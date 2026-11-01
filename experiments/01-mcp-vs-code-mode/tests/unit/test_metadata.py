"""Unit tests for environment and git metadata collection."""

import pytest

from mcp_vs_code_mode.bench.metadata import collect_environment, git_state

pytestmark = pytest.mark.unit


def test_environment_has_required_keys() -> None:
    env = collect_environment()
    assert set(env["hardware"]) == {"machine", "processor", "cpu_count", "memory_gb"}
    assert env["os"]
    assert env["python_version"].startswith("3.")
    assert set(env["package_versions"]) == {
        "mcp",
        "openai",
        "pydantic-monty",
        "pandas",
        "matplotlib",
        "httpx",
    }


def test_git_state_in_this_repo() -> None:
    sha, dirty = git_state()
    assert len(sha) == 40
    assert isinstance(dirty, bool)
