"""Answer extraction and scoring against ground truth."""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from mcp_vs_code_mode.scenarios.definitions import AccountSummary, AnswerA, AnswerB

Outcome = Literal["correct", "incorrect", "invalid_answer"]

_TOLERANCE = 0.01 + 1e-9
_FENCE = re.compile(r"```(?:json)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ScoreResult:
    """Scoring outcome. ``partial_score`` is the fraction of fields correct."""

    outcome: Outcome
    partial_score: float
    field_errors: tuple[str, ...]


def _first_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, index)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the answer object: last fenced block first, else first parseable object."""
    for block in reversed(_FENCE.findall(text)):
        found = _first_object(block)
        if found is not None:
            return found
    return _first_object(text)


def _close(expected: float, actual: float) -> bool:
    return abs(expected - actual) <= _TOLERANCE


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _parse[ModelT: BaseModel](model: type[ModelT], raw_text: str) -> ModelT | str:
    """Return a validated model, or a string describing why the answer is invalid."""
    payload = extract_json_object(raw_text)
    if payload is None:
        return "No JSON object found in answer"
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        fields = ", ".join(sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()}))
        return f"Answer does not match schema: {fields}"


def _result(total: int, errors: list[str]) -> ScoreResult:
    if not errors:
        return ScoreResult("correct", 1.0, ())
    return ScoreResult("incorrect", max(0.0, (total - len(errors)) / total), tuple(errors))


def score_answer_a(expected: AnswerA, raw_text: str) -> ScoreResult:
    """Score a scenario A answer (3 fields)."""
    parsed = _parse(AnswerA, raw_text)
    if isinstance(parsed, str):
        return ScoreResult("invalid_answer", 0.0, (parsed,))
    errors: list[str] = []
    if parsed.account_id != expected.account_id:
        errors.append(f"account_id: expected {expected.account_id}, got {parsed.account_id}")
    if not _close(expected.available_balance, parsed.available_balance):
        errors.append(
            f"available_balance: expected {_fmt(expected.available_balance)}, "
            f"got {_fmt(parsed.available_balance)}"
        )
    if parsed.currency.lower() != expected.currency.lower():
        errors.append(f"currency: expected {expected.currency}, got {parsed.currency}")
    return _result(3, errors)


def _score_account(
    expected: AccountSummary, actual: AccountSummary | None, errors: list[str]
) -> int:
    """Append errors for one account and return its number of fields."""
    prefix = expected.account_id
    field_count = 2 + len(expected.spend_by_category) + 1
    if actual is None:
        names = [
            "available_balance",
            "large_debit_ids",
            *(f"spend_by_category.{c}" for c in expected.spend_by_category),
            "spend_by_category extra",
        ]
        errors.extend(f"{prefix}.{name}: account missing from answer" for name in names)
        return field_count
    if not _close(expected.available_balance, actual.available_balance):
        errors.append(
            f"{prefix}.available_balance: expected {_fmt(expected.available_balance)}, "
            f"got {_fmt(actual.available_balance)}"
        )
    if set(expected.large_debit_ids) != set(actual.large_debit_ids):
        errors.append(
            f"{prefix}.large_debit_ids: expected {sorted(expected.large_debit_ids)}, "
            f"got {sorted(actual.large_debit_ids)}"
        )
    for category, value in expected.spend_by_category.items():
        got = actual.spend_by_category.get(category)
        if got is None:
            errors.append(f"{prefix}.spend_by_category.{category}: expected {_fmt(value)}, missing")
        elif not _close(value, got):
            errors.append(
                f"{prefix}.spend_by_category.{category}: expected {_fmt(value)}, got {_fmt(got)}"
            )
    extra = {c for c, v in actual.spend_by_category.items() if abs(v) > 0.01} - set(
        expected.spend_by_category
    )
    if extra:
        errors.append(f"{prefix}.spend_by_category: unexpected categories {sorted(extra)}")
    return field_count


def score_answer_b(expected: AnswerB, raw_text: str) -> ScoreResult:
    """Score a scenario B answer field by field."""
    parsed = _parse(AnswerB, raw_text)
    if isinstance(parsed, str):
        return ScoreResult("invalid_answer", 0.0, (parsed,))
    errors: list[str] = []
    total = 2
    if parsed.customer_id != expected.customer_id:
        errors.append(f"customer_id: expected {expected.customer_id}, got {parsed.customer_id}")
    if not _close(expected.total_available_balance, parsed.total_available_balance):
        errors.append(
            f"total_available_balance: expected {_fmt(expected.total_available_balance)}, "
            f"got {_fmt(parsed.total_available_balance)}"
        )
    actual_by_id = {a.account_id: a for a in parsed.accounts}
    for account in expected.accounts:
        total += _score_account(account, actual_by_id.get(account.account_id), errors)
    extras = sorted(set(actual_by_id) - {a.account_id for a in expected.accounts})
    if extras:
        total += 1
        errors.append(f"accounts: unexpected extra accounts {extras}")
    return _result(total, errors)
