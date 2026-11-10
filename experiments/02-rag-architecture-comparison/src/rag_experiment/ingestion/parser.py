"""Parse an OpenAPI 3.x YAML file into a small, fully resolved model.

Only what the chunker needs is kept. ``$ref`` handling follows one rule, "resolved one level":

- Parameters, request bodies, responses and headers are substituted by the object they point to.
- A schema that is a ``$ref`` becomes a :class:`SchemaView` named after the reference.
- A *field* whose schema is a ``$ref`` is not expanded: its summary is the reference name.
"""

import hashlib
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict

from rag_experiment.ingestion.pointers import PointerError, pointer, resolve_pointer

logger = logging.getLogger(__name__)

_MAX_REF_DEPTH = 10
_METHOD_ORDER = ("get", "post", "put", "patch", "delete", "head", "options", "trace")

Location = Literal["path", "query", "header", "cookie"]
SecurityRequirement = tuple[tuple[str, tuple[str, ...]], ...]
"""Scheme names with their scopes. Every pair in one requirement is needed together."""


class SpecError(Exception):
    """Base class for specification problems. Messages always carry the file path."""


class EmptySpecError(SpecError):
    """The file is empty or only whitespace."""


class InvalidSpecError(SpecError):
    """The file is not a usable OpenAPI document."""


class UnsupportedSpecError(SpecError):
    """The file is valid in some other dialect that this parser does not handle."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Parameter(_Frozen):
    """One parameter of an operation."""

    name: str
    location: Location
    required: bool
    description: str | None
    schema_summary: str
    pointer: str


class SchemaField(_Frozen):
    """One property of an object schema, resolved one level."""

    name: str
    required: bool
    summary: str
    description: str | None


class SchemaView(_Frozen):
    """A schema reduced to a name, a one-line summary and its fields."""

    name: str | None
    description: str | None
    required: tuple[str, ...]
    fields: tuple[SchemaField, ...]
    summary: str


class MediaContent(_Frozen):
    """The schema offered for one media type."""

    media_type: str
    schema_view: SchemaView | None


class RequestBody(_Frozen):
    """The request body of an operation."""

    required: bool
    description: str | None
    contents: tuple[MediaContent, ...]
    pointer: str


class ResponseHeader(_Frozen):
    """A header returned by a response."""

    name: str
    description: str | None
    summary: str


class Response(_Frozen):
    """One response of an operation."""

    status: str
    description: str | None
    headers: tuple[ResponseHeader, ...]
    contents: tuple[MediaContent, ...]
    pointer: str


class Operation(_Frozen):
    """One HTTP operation."""

    path: str
    method: str
    operation_id: str
    summary: str | None
    description: str | None
    tags: tuple[str, ...]
    deprecated: bool
    parameters: tuple[Parameter, ...]
    request_body: RequestBody | None
    responses: tuple[Response, ...]
    security: tuple[SecurityRequirement, ...]
    pointer: str


class OAuthFlow(_Frozen):
    """One OAuth 2.0 flow of a security scheme."""

    flow: str
    token_url: str | None
    scopes: tuple[tuple[str, str], ...]


class SecurityScheme(_Frozen):
    """An entry of ``components.securitySchemes``."""

    name: str
    type: str
    description: str | None
    scheme: str | None
    bearer_format: str | None
    location: str | None
    header_name: str | None
    flows: tuple[OAuthFlow, ...]
    pointer: str


class ComponentSchema(_Frozen):
    """An entry of ``components.schemas``."""

    name: str
    view: SchemaView
    pointer: str


class ParsedSpec(_Frozen):
    """A whole specification file."""

    document_id: str
    title: str
    version: str
    openapi_version: str
    description: str | None
    operations: tuple[Operation, ...]
    component_schemas: tuple[ComponentSchema, ...]
    security_schemes: tuple[SecurityScheme, ...]
    raw_checksum: str


# --------------------------------------------------------------------------- rendering helpers


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def schema_summary(schema: Mapping[str, object]) -> str:
    """Render a schema as one deterministic line, e.g. ``integer, default 100, min 1, max 500``."""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _ref_name(ref)
    raw_type = schema.get("type")
    nullable = False
    if isinstance(raw_type, list):
        names = [str(t) for t in raw_type]
        nullable = "null" in names
        names = [n for n in names if n != "null"]
        type_text = "|".join(names) if names else "null"
    elif isinstance(raw_type, str):
        type_text = raw_type
    else:
        type_text = "object" if "properties" in schema else "any"
    if type_text == "array":
        items = schema.get("items")
        if isinstance(items, Mapping):
            type_text = f"array of {schema_summary(items)}"
    parts = [type_text]
    if "format" in schema:
        parts.append(f"format {schema['format']}")
    enum = schema.get("enum")
    if isinstance(enum, list):
        parts.append("enum " + "|".join(_render_value(e) for e in enum))
    if "default" in schema:
        parts.append(f"default {_render_value(schema['default'])}")
    for key, label in (
        ("minimum", "min"),
        ("maximum", "max"),
        ("minLength", "min length"),
        ("maxLength", "max length"),
    ):
        if key in schema:
            parts.append(f"{label} {_render_value(schema[key])}")
    if nullable:
        parts.append("nullable")
    return ", ".join(parts)


def _slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")


def _parameter_location(value: object) -> Location | None:
    for location in get_args(Location):
        if value == location:
            return location  # type: ignore[no-any-return]
    return None


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


# --------------------------------------------------------------------------- parser


class _Parser:
    def __init__(self, path: Path, root: Mapping[str, object]) -> None:
        self.path = path
        self.root = root

    def fail(self, message: str) -> InvalidSpecError:
        return InvalidSpecError(f"{self.path}: {message}")

    # -- references

    def check_refs(self, node: object, where: str = "#") -> None:
        """Reject non-local references and references that do not resolve."""
        if isinstance(node, Mapping):
            ref = node.get("$ref")
            if isinstance(ref, str):
                if not ref.startswith("#/"):
                    raise UnsupportedSpecError(
                        f"{self.path}: non-local $ref {ref!r} at {where} is not supported"
                    )
                try:
                    resolve_pointer(self.root, ref)
                except PointerError as exc:
                    raise self.fail(f"$ref {ref!r} at {where} does not resolve") from exc
            for key, value in node.items():
                self.check_refs(value, f"{where}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                self.check_refs(value, f"{where}/{i}")

    def deref(self, obj: object) -> tuple[Mapping[str, object], str | None]:
        """Follow a ``$ref`` chain. Returns the target and the last reference name, if any."""
        name: str | None = None
        for _ in range(_MAX_REF_DEPTH + 1):
            if not isinstance(obj, Mapping):
                raise self.fail(f"expected an object, found {type(obj).__name__}")
            ref = obj.get("$ref")
            if not isinstance(ref, str):
                return obj, name
            name = _ref_name(ref)
            try:
                obj = resolve_pointer(self.root, ref)
            except PointerError as exc:
                raise self.fail(f"$ref {ref!r} does not resolve") from exc
        raise self.fail(f"$ref chain deeper than {_MAX_REF_DEPTH} (cycle?)")

    # -- schemas

    def _fields(
        self, schema: Mapping[str, object]
    ) -> tuple[tuple[str, ...], tuple[SchemaField, ...]]:
        required_raw = schema.get("required")
        required = tuple(str(r) for r in required_raw) if isinstance(required_raw, list) else ()
        props = schema.get("properties")
        fields: list[SchemaField] = []
        if isinstance(props, Mapping):
            for name, prop in props.items():
                if not isinstance(prop, Mapping):
                    raise self.fail(f"property {name!r} is not an object")
                fields.append(
                    SchemaField(
                        name=str(name),
                        required=str(name) in required,
                        summary=schema_summary(prop),
                        description=_opt_str(prop.get("description")),
                    )
                )
        return required, tuple(fields)

    def schema_view(self, schema_obj: object, name_hint: str | None = None) -> SchemaView:
        """Build a view of a schema; a ``$ref`` makes the view named after the reference."""
        schema, ref_name = self.deref(schema_obj)
        name = name_hint if name_hint is not None else ref_name
        description = _opt_str(schema.get("description"))
        if schema.get("type") == "array" and isinstance(schema.get("items"), Mapping):
            items = schema["items"]
            assert isinstance(items, Mapping)
            item, _ = self.deref(items)
            required, fields = self._fields(item)
            return SchemaView(
                name=name,
                description=description,
                required=required,
                fields=fields,
                summary=schema_summary(schema),
            )
        required, fields = self._fields(schema)
        summary = ref_name if ref_name is not None and name_hint is None else schema_summary(schema)
        return SchemaView(
            name=name, description=description, required=required, fields=fields, summary=summary
        )

    def contents(self, content: object) -> tuple[MediaContent, ...]:
        if content is None:
            return ()
        if not isinstance(content, Mapping):
            raise self.fail("'content' is not an object")
        result: list[MediaContent] = []
        for media_type, media in content.items():
            if not isinstance(media, Mapping):
                raise self.fail(f"content entry {media_type!r} is not an object")
            schema = media.get("schema")
            view = self.schema_view(schema) if schema is not None else None
            result.append(MediaContent(media_type=str(media_type), schema_view=view))
        return tuple(result)

    # -- operation parts

    def parameter(self, raw: object, op_pointer: str) -> Parameter:
        param, _ = self.deref(raw)
        location = _parameter_location(param.get("in"))
        if location is None:
            raise self.fail(f"parameter {param.get('name')!r} has a bad 'in': {param.get('in')!r}")
        schema = param.get("schema")
        summary = schema_summary(schema) if isinstance(schema, Mapping) else "any"
        description = _opt_str(param.get("description"))
        if description is None:
            logger.debug("%s: parameter %r has no description", self.path, param.get("name"))
        return Parameter(
            name=str(param.get("name")),
            location=location,
            required=True if location == "path" else bool(param.get("required", False)),
            description=description,
            schema_summary=summary,
            pointer=op_pointer + "/parameters",
        )

    def request_body(self, raw: object, op_pointer: str) -> RequestBody:
        body, _ = self.deref(raw)
        return RequestBody(
            required=bool(body.get("required", False)),
            description=_opt_str(body.get("description")),
            contents=self.contents(body.get("content")),
            pointer=op_pointer + "/requestBody",
        )

    def response(self, status: str, raw: object, op_pointer: str) -> Response:
        resp, _ = self.deref(raw)
        headers: list[ResponseHeader] = []
        raw_headers = resp.get("headers")
        if isinstance(raw_headers, Mapping):
            for header_name, raw_header in raw_headers.items():
                header, _ = self.deref(raw_header)
                schema = header.get("schema")
                headers.append(
                    ResponseHeader(
                        name=str(header_name),
                        description=_opt_str(header.get("description")),
                        summary=schema_summary(schema) if isinstance(schema, Mapping) else "any",
                    )
                )
        return Response(
            status=status,
            description=_opt_str(resp.get("description")),
            headers=tuple(headers),
            contents=self.contents(resp.get("content")),
            pointer=f"{op_pointer}/responses/{status}",
        )

    def security(self, raw: object) -> tuple[SecurityRequirement, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise self.fail("'security' is not a list")
        alternatives: list[SecurityRequirement] = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise self.fail("a security requirement is not an object")
            pairs: list[tuple[str, tuple[str, ...]]] = []
            for scheme_name, scopes in item.items():
                scope_list = tuple(str(s) for s in scopes) if isinstance(scopes, list) else ()
                pairs.append((str(scheme_name), scope_list))
            alternatives.append(tuple(pairs))
        return tuple(alternatives)

    def operation(
        self, path: str, method: str, raw: object, path_params: list[object]
    ) -> Operation:
        if not isinstance(raw, Mapping):
            raise self.fail(f"operation {method.upper()} {path} is not an object")
        op_pointer = pointer("paths", path, method)
        operation_id = raw.get("operationId")
        if not isinstance(operation_id, str) or not operation_id:
            operation_id = f"{method}_{_slug(path)}"
            logger.warning(
                "%s: %s %s has no operationId; using %s", self.path, method, path, operation_id
            )
        description = _opt_str(raw.get("description"))
        summary = _opt_str(raw.get("summary"))
        if description is None:
            logger.debug("%s: %s has no description", self.path, operation_id)

        op_params_raw = raw.get("parameters")
        op_params = op_params_raw if isinstance(op_params_raw, list) else []
        merged: dict[tuple[str, str], Parameter] = {}
        for item in [*path_params, *op_params]:
            parsed = self.parameter(item, op_pointer)
            merged[(parsed.name, parsed.location)] = parsed  # later (operation-level) wins

        request_body = (
            self.request_body(raw["requestBody"], op_pointer) if "requestBody" in raw else None
        )
        responses_raw = raw.get("responses")
        responses: list[Response] = []
        if isinstance(responses_raw, Mapping):
            for status in sorted(str(s) for s in responses_raw):
                original = next(k for k in responses_raw if str(k) == status)
                responses.append(self.response(status, responses_raw[original], op_pointer))

        if "security" in raw:
            security = self.security(raw["security"])
        else:
            security = self.security(self.root.get("security"))

        tags_raw = raw.get("tags")
        tags = tuple(str(t) for t in tags_raw) if isinstance(tags_raw, list) else ()
        return Operation(
            path=path,
            method=method.upper(),
            operation_id=operation_id,
            summary=summary,
            description=description,
            tags=tags,
            deprecated=bool(raw.get("deprecated", False)),
            parameters=tuple(merged.values()),
            request_body=request_body,
            responses=tuple(responses),
            security=security,
            pointer=op_pointer,
        )

    def operations(self, paths: Mapping[str, object]) -> tuple[Operation, ...]:
        found: list[Operation] = []
        for path in sorted(paths):
            item = paths[path]
            if not isinstance(item, Mapping):
                raise self.fail(f"path item {path!r} is not an object")
            shared = item.get("parameters")
            path_params = shared if isinstance(shared, list) else []
            for method in _METHOD_ORDER:
                if method in item:
                    found.append(self.operation(str(path), method, item[method], path_params))
        return tuple(found)

    # -- components

    def security_schemes(self) -> tuple[SecurityScheme, ...]:
        components = self.root.get("components")
        raw_schemes = components.get("securitySchemes") if isinstance(components, Mapping) else None
        if not isinstance(raw_schemes, Mapping):
            return ()
        result: list[SecurityScheme] = []
        for name, raw in raw_schemes.items():
            scheme, _ = self.deref(raw)
            flows: list[OAuthFlow] = []
            raw_flows = scheme.get("flows")
            if isinstance(raw_flows, Mapping):
                for flow_name, flow in raw_flows.items():
                    if not isinstance(flow, Mapping):
                        raise self.fail(f"OAuth flow {flow_name!r} is not an object")
                    raw_scopes = flow.get("scopes")
                    scopes = (
                        tuple((str(k), str(v)) for k, v in raw_scopes.items())
                        if isinstance(raw_scopes, Mapping)
                        else ()
                    )
                    flows.append(
                        OAuthFlow(
                            flow=str(flow_name),
                            token_url=_opt_str(flow.get("tokenUrl")),
                            scopes=scopes,
                        )
                    )
            result.append(
                SecurityScheme(
                    name=str(name),
                    type=str(scheme.get("type", "")),
                    description=_opt_str(scheme.get("description")),
                    scheme=_opt_str(scheme.get("scheme")),
                    bearer_format=_opt_str(scheme.get("bearerFormat")),
                    location=_opt_str(scheme.get("in")),
                    header_name=_opt_str(scheme.get("name")),
                    flows=tuple(flows),
                    pointer=pointer("components", "securitySchemes", str(name)),
                )
            )
        return tuple(result)

    def component_schemas(self) -> tuple[ComponentSchema, ...]:
        components = self.root.get("components")
        raw_schemas = components.get("schemas") if isinstance(components, Mapping) else None
        if not isinstance(raw_schemas, Mapping):
            return ()
        return tuple(
            ComponentSchema(
                name=str(name),
                view=self.schema_view(raw, name_hint=str(name)),
                pointer=pointer("components", "schemas", str(name)),
            )
            for name, raw in raw_schemas.items()
        )


def load_raw(path: Path) -> dict[str, object]:
    """Load a spec file as plain YAML data, with the same validation as :func:`parse_spec`."""
    data = path.read_bytes()
    if not data.strip():
        raise EmptySpecError(f"{path}: file is empty")
    try:
        loaded = yaml.safe_load(data)
    except yaml.YAMLError as exc:
        raise InvalidSpecError(f"{path}: not valid YAML ({exc})") from exc
    if not isinstance(loaded, dict):
        raise InvalidSpecError(f"{path}: the top level must be a mapping")
    return loaded


def parse_spec(path: Path) -> ParsedSpec:
    """Parse one OpenAPI 3.x YAML file. Raises a :class:`SpecError` subclass on bad input."""
    root = load_raw(path)
    if "swagger" in root:
        raise UnsupportedSpecError(f"{path}: Swagger 2.0 documents are not supported")
    openapi = root.get("openapi")
    if not isinstance(openapi, str):
        raise InvalidSpecError(f"{path}: missing 'openapi' version")
    if not openapi.startswith("3."):
        raise UnsupportedSpecError(f"{path}: unsupported OpenAPI version {openapi!r}")
    info = root.get("info")
    if not isinstance(info, Mapping) or not isinstance(info.get("title"), str):
        raise InvalidSpecError(f"{path}: missing 'info.title'")
    if "paths" not in root:
        raise InvalidSpecError(f"{path}: missing 'paths'")
    paths = root["paths"]
    if not isinstance(paths, Mapping):
        raise InvalidSpecError(f"{path}: 'paths' must be a mapping")

    parser = _Parser(path, root)
    parser.check_refs(root)
    return ParsedSpec(
        document_id=path.stem,
        title=str(info["title"]),
        version=str(info.get("version", "")),
        openapi_version=openapi,
        description=_opt_str(info.get("description")),
        operations=parser.operations(paths),
        component_schemas=parser.component_schemas(),
        security_schemes=parser.security_schemes(),
        raw_checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
