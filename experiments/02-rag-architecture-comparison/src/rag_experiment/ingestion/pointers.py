"""RFC 6901 JSON Pointer helpers.

Pointers are written in the plain string form ``#/a/b`` (not percent-encoded), so ``{accountId}``
stays readable. A *source* is a document id plus a pointer, written ``document#/pointer``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class PointerError(KeyError):
    """Raised when a pointer segment does not exist in a document."""


def escape_segment(segment: str) -> str:
    """Escape one pointer segment: ``~`` becomes ``~0``, then ``/`` becomes ``~1``."""
    return segment.replace("~", "~0").replace("/", "~1")


def unescape_segment(segment: str) -> str:
    """Undo :func:`escape_segment`: ``~1`` first, then ``~0``."""
    return segment.replace("~1", "/").replace("~0", "~")


def pointer(*segments: str | int) -> str:
    """Build a pointer from raw segments. No segments give ``#``."""
    if not segments:
        return "#"
    return "#/" + "/".join(escape_segment(str(s)) for s in segments)


def split_pointer(p: str) -> tuple[str, ...]:
    """Split a pointer into unescaped segments. Requires a ``#/`` prefix, or exactly ``#``."""
    if p == "#":
        return ()
    if not p.startswith("#/"):
        raise ValueError(f"Not a JSON pointer (expected a '#/' prefix): {p!r}")
    return tuple(unescape_segment(s) for s in p[2:].split("/"))


def resolve_pointer(doc: Mapping[str, object], p: str) -> object:
    """Return the element a pointer addresses; numeric segments index lists."""
    node: object = doc
    for segment in split_pointer(p):
        if isinstance(node, Mapping):
            if segment not in node:
                raise PointerError(f"Segment {segment!r} not found while resolving {p!r}")
            node = node[segment]
        elif isinstance(node, Sequence) and not isinstance(node, str):
            try:
                node = node[int(segment)]
            except (ValueError, IndexError) as exc:
                raise PointerError(f"Bad list index {segment!r} while resolving {p!r}") from exc
        else:
            raise PointerError(f"Cannot descend into a scalar at {segment!r} in {p!r}")
    return node


def is_prefix(prefix: str, p: str) -> bool:
    """True if ``prefix`` is a whole-segment prefix of ``p`` (equal pointers count)."""
    a = split_pointer(prefix)
    b = split_pointer(p)
    return len(a) <= len(b) and b[: len(a)] == a


@dataclass(frozen=True)
class Source:
    """A labelled spec element: a document id and a pointer inside that document."""

    document_id: str
    pointer: str

    def __str__(self) -> str:
        return f"{self.document_id}{self.pointer}"


def parse_source(text: str) -> Source:
    """Parse ``document#/pointer``; raises ``ValueError`` on a bad format."""
    document_id, hash_sign, rest = text.partition("#")
    if not hash_sign or not document_id:
        raise ValueError(f"Bad source {text!r}: expected 'document#/pointer'")
    p = "#" + rest
    split_pointer(p)  # validates the pointer part
    return Source(document_id=document_id, pointer=p)
