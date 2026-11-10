"""Structure-aware chunking: one chunk per operation, parameter list, body, response and component.

The content templates are fixed so that chunk text is stable and easy to inspect. Splitting only
happens when a chunk exceeds the configured size, and only between bullet lines.
"""

import hashlib
import logging
import re
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from rag_experiment.config import ChunkingConfig
from rag_experiment.ingestion.parser import (
    MediaContent,
    Operation,
    ParsedSpec,
    SchemaView,
    SecurityRequirement,
    SecurityScheme,
)
from rag_experiment.ingestion.pointers import Source

if TYPE_CHECKING:
    from rag_experiment.corpus import Corpus

logger = logging.getLogger(__name__)

ChunkType = Literal[
    "operation", "parameters", "request_body", "response", "security_scheme", "component_schema"
]


class Chunk(BaseModel):
    """One retrievable piece of a specification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    document_name: str
    chunk_id: str
    chunk_type: ChunkType
    api_path: str | None
    http_method: str | None
    operation_id: str | None
    tags: tuple[str, ...]
    content: str
    source_reference: str
    refs: tuple[str, ...]
    spec_version: str
    content_hash: str

    @property
    def source(self) -> Source:
        """The spec element this chunk was built from."""
        return Source(document_id=self.document_id, pointer=self.source_reference)


# --------------------------------------------------------------------------- text helpers


def _req(flag: bool) -> str:
    return "required" if flag else "optional"


def _bullet(head: str, description: str | None) -> str:
    return f"- {head}: {description}" if description else f"- {head}"


def _field_lines(view: SchemaView) -> list[str]:
    return [
        _bullet(f"{f.name} ({f.summary}, {_req(f.required)})", f.description) for f in view.fields
    ]


def _content_lines(contents: Iterable[MediaContent], with_required: bool) -> list[str]:
    lines: list[str] = []
    for content in contents:
        view = content.schema_view
        if view is None:
            lines.append(f"Content {content.media_type}")
            continue
        lines.append(f"Content {content.media_type}: {view.summary}")
        if with_required and view.required:
            lines.append("Required fields: " + ", ".join(view.required))
        lines.extend(_field_lines(view))
    return lines


def _render_requirement(
    requirement: SecurityRequirement, schemes: dict[str, SecurityScheme]
) -> str:
    rendered: list[str] = []
    for name, scopes in requirement:
        scheme = schemes.get(name)
        if scheme is None:
            rendered.append(name)
        elif scheme.type == "oauth2":
            scope_text = f"; scopes: {', '.join(scopes)}" if scopes else ""
            rendered.append(f"{name} (OAuth2 bearer token in the Authorization header{scope_text})")
        elif scheme.type == "apiKey":
            rendered.append(f"{name} (API key in {scheme.location} {scheme.header_name})")
        elif scheme.type == "http":
            rendered.append(f"{name} (HTTP {scheme.scheme})")
        else:
            rendered.append(name)
    return " AND ".join(rendered)


def _summary_tokens(summaries: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for summary in summaries:
        tokens.update(re.findall(r"[A-Za-z0-9_]+", summary))
    return tokens


def _view_summaries(views: Iterable[SchemaView | None]) -> list[str]:
    summaries: list[str] = []
    for view in views:
        if view is not None:
            summaries.append(view.summary)
            summaries.extend(f.summary for f in view.fields)
    return summaries


# --------------------------------------------------------------------------- splitting


def _split(lines: list[str], limit: int) -> list[list[str]]:
    """Split lines into parts that each fit ``limit``, cutting only before bullet lines."""
    if len("\n".join(lines)) <= limit:
        return [lines]
    first_bullet = next((i for i, line in enumerate(lines) if line.startswith("- ")), None)
    if first_bullet is None:
        logger.warning(
            "chunk of %d chars has no bullet lines and stays whole", len("\n".join(lines))
        )
        return [lines]
    header = lines[:first_bullet]
    units: list[list[str]] = []
    pending: list[str] = []
    for line in lines[first_bullet:]:
        pending.append(line)
        if line.startswith("- "):
            units.append(pending)
            pending = []
    if pending:  # trailing non-bullet lines belong with the last unit
        units[-1].extend(pending)

    parts: list[list[str]] = []
    current: list[str] = []
    for unit in units:
        candidate = [*header, *current, *unit]
        if current and len("\n".join(candidate)) > limit:
            parts.append([*header, *current])
            current = []
        current.extend(unit)
    if current:
        parts.append([*header, *current])
    for part in parts:
        if len("\n".join(part)) > limit:
            logger.warning(
                "a single bullet makes a %d char chunk; keeping it whole", len("\n".join(part))
            )
    return parts


# --------------------------------------------------------------------------- chunk building


class _Builder:
    def __init__(self, spec: ParsedSpec, config: ChunkingConfig) -> None:
        self.spec = spec
        self.limit = config.max_chunk_chars
        self.schemes = {s.name: s for s in spec.security_schemes}
        self.component_names = {c.name for c in spec.component_schemas}
        self.chunks: list[Chunk] = []

    def _refs(self, summaries: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted(_summary_tokens(summaries) & self.component_names))

    def _emit(
        self,
        *,
        base_id: str,
        chunk_type: ChunkType,
        lines: list[str],
        source_reference: str,
        refs: tuple[str, ...],
        operation: Operation | None,
    ) -> None:
        parts = _split(lines, self.limit)
        for index, part in enumerate(parts, start=1):
            content = "\n".join(part)
            self.chunks.append(
                Chunk(
                    document_id=self.spec.document_id,
                    document_name=self.spec.title,
                    chunk_id=base_id if len(parts) == 1 else f"{base_id}:p{index}",
                    chunk_type=chunk_type,
                    api_path=operation.path if operation else None,
                    http_method=operation.method if operation else None,
                    operation_id=operation.operation_id if operation else None,
                    tags=operation.tags if operation else (),
                    content=content,
                    source_reference=source_reference,
                    refs=refs,
                    spec_version=self.spec.version,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
            )

    def _title(self, op: Operation, label: str) -> str:
        return f"[{self.spec.document_id}] {op.method} {op.path} · {label}"

    def operation(self, op: Operation) -> None:
        doc = self.spec.document_id
        lines = [self._title(op, "operation"), f"operationId: {op.operation_id}"]
        if op.summary:
            lines.append(f"Summary: {op.summary}")
        if op.description:
            lines.append(f"Description: {op.description}")
        if op.tags:
            lines.append("Tags: " + ", ".join(op.tags))
        if op.deprecated:
            lines.append("Deprecated: yes")
        security = " OR ".join(_render_requirement(r, self.schemes) for r in op.security)
        lines.append(f"Security: {security or 'none'}")
        if op.parameters:
            lines.append(
                "Parameters: " + ", ".join(f"{p.name} ({p.location})" for p in op.parameters)
            )
        body_refs: list[str] = []
        if op.request_body is not None and op.request_body.contents:
            media = [
                f"{c.media_type}: {c.schema_view.summary if c.schema_view else 'no schema'}"
                for c in op.request_body.contents
            ]
            lines.append("Request body: " + "; ".join(media))
            body_refs = [c.schema_view.summary for c in op.request_body.contents if c.schema_view]
        if op.responses:
            lines.append("Responses: " + ", ".join(r.status for r in op.responses))
        self._emit(
            base_id=f"{doc}:{op.operation_id}:operation",
            chunk_type="operation",
            lines=lines,
            source_reference=op.pointer,
            refs=self._refs(body_refs),
            operation=op,
        )

        if op.parameters:
            plines = [self._title(op, "parameters")]
            for p in op.parameters:
                head = f"{p.name} ({p.location}, {_req(p.required)}, {p.schema_summary})"
                plines.append(_bullet(head, p.description))
            self._emit(
                base_id=f"{doc}:{op.operation_id}:parameters",
                chunk_type="parameters",
                lines=plines,
                source_reference=f"{op.pointer}/parameters",
                refs=self._refs(p.schema_summary for p in op.parameters),
                operation=op,
            )

        if op.request_body is not None:
            body = op.request_body
            blines = [self._title(op, "request body")]
            blines.append(_bullet_free(f"Request body ({_req(body.required)})", body.description))
            blines.extend(_content_lines(body.contents, with_required=True))
            self._emit(
                base_id=f"{doc}:{op.operation_id}:request_body",
                chunk_type="request_body",
                lines=blines,
                source_reference=body.pointer,
                refs=self._refs(_view_summaries(c.schema_view for c in body.contents)),
                operation=op,
            )

        for response in op.responses:
            rlines = [self._title(op, f"response {response.status}")]
            rlines.append(_bullet_free(f"Response {response.status}", response.description))
            if response.headers:
                rlines.append("Headers:")
                rlines.extend(
                    _bullet(f"{h.name} ({h.summary})", h.description) for h in response.headers
                )
            rlines.extend(_content_lines(response.contents, with_required=False))
            self._emit(
                base_id=f"{doc}:{op.operation_id}:response:{response.status}",
                chunk_type="response",
                lines=rlines,
                source_reference=response.pointer,
                refs=self._refs(_view_summaries(c.schema_view for c in response.contents)),
                operation=op,
            )

    def security_scheme(self, scheme: SecurityScheme) -> None:
        lines = [f"[{self.spec.document_id}] security scheme {scheme.name}", f"Type: {scheme.type}"]
        if scheme.description:
            lines.append(f"Description: {scheme.description}")
        if scheme.type == "http":
            if scheme.scheme:
                lines.append(f"HTTP scheme: {scheme.scheme}")
            if scheme.bearer_format:
                lines.append(f"Bearer format: {scheme.bearer_format}")
        if scheme.type == "apiKey":
            lines.append(f"API key: {scheme.location} {scheme.header_name}")
        for flow in scheme.flows:
            lines.append(
                f"Flow {flow.flow}: token URL {flow.token_url}"
                if flow.token_url
                else f"Flow {flow.flow}"
            )
            lines.extend(f"- scope {name}: {text}" for name, text in flow.scopes)
        self._emit(
            base_id=f"{self.spec.document_id}:{scheme.name}:security_scheme",
            chunk_type="security_scheme",
            lines=lines,
            source_reference=scheme.pointer,
            refs=(),
            operation=None,
        )

    def component_schema(self, name: str, view: SchemaView, source_reference: str) -> None:
        lines = [
            f"[{self.spec.document_id}] component schema {name}",
            f"Schema {name}: {view.summary}",
        ]
        if view.description:
            lines.append(f"Description: {view.description}")
        if view.required:
            lines.append("Required fields: " + ", ".join(view.required))
        lines.extend(_field_lines(view))
        self._emit(
            base_id=f"{self.spec.document_id}:{name}:component_schema",
            chunk_type="component_schema",
            lines=lines,
            source_reference=source_reference,
            refs=self._refs(f.summary for f in view.fields),
            operation=None,
        )


def _bullet_free(head: str, description: str | None) -> str:
    return f"{head}: {description}" if description else head


def chunk_spec(spec: ParsedSpec, config: ChunkingConfig) -> list[Chunk]:
    """Chunk one spec in a deterministic order.

    Operations come first, each as operation, parameters, request body and responses in status
    order. Security schemes follow in name order, then component schemas in name order.
    """
    builder = _Builder(spec, config)
    for op in spec.operations:
        builder.operation(op)
    for scheme in sorted(spec.security_schemes, key=lambda s: s.name):
        builder.security_scheme(scheme)
    for component in sorted(spec.component_schemas, key=lambda c: c.name):
        builder.component_schema(component.name, component.view, component.pointer)
    _check_unique(builder.chunks)
    return builder.chunks


def chunk_corpus(corpus: "Corpus", config: ChunkingConfig) -> list[Chunk]:
    """Chunk every spec, documents in ``document_id`` order. Chunk ids are unique corpus-wide."""
    chunks: list[Chunk] = []
    for spec in sorted(corpus.specs, key=lambda s: s.document_id):
        chunks.extend(chunk_spec(spec, config))
    _check_unique(chunks)
    return chunks


def _check_unique(chunks: Sequence[Chunk]) -> None:
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_id in seen:
            raise ValueError(f"Duplicate chunk_id: {chunk.chunk_id}")
        seen.add(chunk.chunk_id)
