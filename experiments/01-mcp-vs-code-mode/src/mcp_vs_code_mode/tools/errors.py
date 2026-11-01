"""Tool-level errors with a stable, model-facing payload shape."""

from typing import ClassVar


class ToolError(Exception):
    """Base class for errors returned to the model as tool errors."""

    error_type: ClassVar[str] = "tool_error"

    def to_payload(self) -> dict[str, dict[str, str]]:
        """Return the JSON-compatible error payload."""
        return {"error": {"type": self.error_type, "message": str(self)}}


class UnknownToolError(ToolError):
    """The requested tool is not on the allowlist."""

    error_type = "unknown_tool"


class ToolInputError(ToolError):
    """The tool arguments failed validation."""

    error_type = "invalid_input"


class ToolAccessError(ToolError):
    """The principal is not allowed to perform the operation."""

    error_type = "access_denied"


class ToolNotFoundError(ToolError):
    """The referenced resource does not exist."""

    error_type = "not_found"
