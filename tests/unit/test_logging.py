"""Tests for logging configuration."""

import logging
from collections.abc import Iterator

import pytest

from ai_lab.utils import configure_logging

pytestmark = pytest.mark.unit


@pytest.fixture
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    original_level = root.level
    original_handlers = root.handlers[:]
    yield
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


@pytest.mark.usefixtures("restore_root_logger")
def test_configure_logging_sets_root_level() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="Unknown log level"):
        configure_logging("LOUD")
