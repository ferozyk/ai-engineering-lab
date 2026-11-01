"""Shared fixtures for experiment 01 tests."""

import pytest

from mcp_vs_code_mode.banking import (
    AuditLog,
    BankingService,
    Dataset,
    Principal,
    benchmark_principal,
    generate_dataset,
)
from mcp_vs_code_mode.tools import ToolExecutor


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    """The default synthetic dataset, generated once per session."""
    return generate_dataset()


@pytest.fixture
def audit_log() -> AuditLog:
    """A fresh in-memory audit log."""
    return AuditLog()


@pytest.fixture
def service(dataset: Dataset, audit_log: AuditLog) -> BankingService:
    """Banking service over the default dataset."""
    return BankingService(dataset, audit_log)


@pytest.fixture
def principal() -> Principal:
    """The benchmark principal."""
    return benchmark_principal()


@pytest.fixture
def executor(service: BankingService, principal: Principal) -> ToolExecutor:
    """Tool executor on the test channel."""
    return ToolExecutor(service, principal, "test")
