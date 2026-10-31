"""Shared foundations for AI Engineering Lab experiments."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ai-engineering-lab")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled checkout
    __version__ = "0.0.0"

__all__ = ["__version__"]
