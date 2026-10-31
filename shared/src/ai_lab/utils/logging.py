"""Logging helpers.

Never log secrets. JSON/structured output can be added when an experiment needs it.
"""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a plain-text format.

    Raises ValueError if ``level`` is not a known logging level name.
    """
    if level not in logging.getLevelNamesMapping():
        raise ValueError(f"Unknown log level: {level!r}")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
