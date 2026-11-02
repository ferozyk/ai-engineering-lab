"""Unit tests for answer extraction and scoring."""

import json
from typing import Any

import pytest

from mcp_vs_code_mode.scenarios import (
    AccountSummary,
    AnswerA,
    AnswerB,
    AnswerC,
    MerchantTotal,
    extract_json_object,
    score_answer_a,
    score_answer_b,
    score_answer_c,
)

pytestmark = pytest.mark.unit

EXPECTED_A = AnswerA(account_id="ACC-0050-1", available_balance=1234.56, currency="USD")
EXPECTED_B = AnswerB(
    customer_id="CUST-0010",
    accounts=[
        AccountSummary(
            account_id="ACC-0010-1",
            available_balance=1000.10,
            spend_by_category={"dining": 1500.00, "groceries": 30.01},
            large_debit_ids=["TXN-0010-1-0004"],
        ),
        AccountSummary(
            account_id="ACC-0010-2",
            available_balance=2000.25,
            spend_by_category={"utilities": 45.50},
            large_debit_ids=[],
        ),
    ],
    total_available_balance=3000.35,
)


def _b(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXPECTED_B.model_dump_json())
    data.update(changes)
    return data


def _score_b(data: Any) -> Any:
    return score_answer_b(EXPECTED_B, json.dumps(data))


def test_exact_answers_correct() -> None:
    a = score_answer_a(EXPECTED_A, EXPECTED_A.model_dump_json())
    assert (a.outcome, a.partial_score, a.field_errors) == ("correct", 1.0, ())
    b = score_answer_b(EXPECTED_B, EXPECTED_B.model_dump_json())
    assert (b.outcome, b.partial_score, b.field_errors) == ("correct", 1.0, ())


def test_fenced_answer_with_prose() -> None:
    text = f"Here you go:\n```json\n{EXPECTED_A.model_dump_json()}\n```\nHope that helps {{x}}."
    assert score_answer_a(EXPECTED_A, text).outcome == "correct"


def test_last_fence_wins() -> None:
    text = (
        '```json\n{"account_id": "x"}\n```\nfinal:\n```\n' + EXPECTED_A.model_dump_json() + "\n```"
    )
    assert score_answer_a(EXPECTED_A, text).outcome == "correct"


def test_extract_json_object_from_prose() -> None:
    assert extract_json_object('answer is {"a": 1} ok') == {"a": 1}
    assert extract_json_object("nothing here") is None
    assert extract_json_object("[1, 2]") is None


def test_tolerance_a() -> None:
    near = EXPECTED_A.model_copy(update={"available_balance": 1234.561})
    assert score_answer_a(EXPECTED_A, near.model_dump_json()).outcome == "correct"
    far = json.dumps({**EXPECTED_A.model_dump(), "available_balance": 1234.58})
    result = score_answer_a(EXPECTED_A, far)
    assert result.outcome == "incorrect"
    assert result.field_errors[0].startswith("available_balance")
    assert result.partial_score == pytest.approx(2 / 3)


def test_currency_case_insensitive() -> None:
    text = json.dumps({**EXPECTED_A.model_dump(), "currency": "usd"})
    assert score_answer_a(EXPECTED_A, text).outcome == "correct"


def test_tolerance_b() -> None:
    data = _b()
    data["total_available_balance"] = 3000.355
    assert _score_b(data).outcome == "correct"
    data["accounts"][0]["spend_by_category"]["dining"] = 1500.02
    result = _score_b(data)
    assert result.outcome == "incorrect"
    assert any(e.startswith("ACC-0010-1.spend_by_category.dining") for e in result.field_errors)
    assert "expected 1500.00, got 1500.02" in result.field_errors[0]


def test_zero_valued_extra_category_ok() -> None:
    data = _b()
    data["accounts"][1]["spend_by_category"]["dining"] = 0.0
    assert _score_b(data).outcome == "correct"


def test_nonzero_extra_category_incorrect() -> None:
    data = _b()
    data["accounts"][1]["spend_by_category"]["dining"] = 5.0
    result = _score_b(data)
    assert result.outcome == "incorrect"
    assert len(result.field_errors) == 1
    assert "unexpected categories" in result.field_errors[0]


def test_missing_category_single_error() -> None:
    data = _b()
    del data["accounts"][0]["spend_by_category"]["groceries"]
    result = _score_b(data)
    assert result.outcome == "incorrect"
    assert len(result.field_errors) == 1
    assert result.field_errors[0].startswith("ACC-0010-1.spend_by_category.groceries")


def test_account_order_irrelevant() -> None:
    data = _b()
    data["accounts"].reverse()
    assert _score_b(data).outcome == "correct"


def test_missing_account() -> None:
    data = _b()
    data["accounts"].pop()
    result = _score_b(data)
    assert result.outcome == "incorrect"
    assert 0.0 < result.partial_score < 1.0
    assert all(e.startswith("ACC-0010-2") for e in result.field_errors)


def test_wrong_large_debit_ids() -> None:
    data = _b()
    data["accounts"][0]["large_debit_ids"] = []
    result = _score_b(data)
    assert result.outcome == "incorrect"
    assert result.partial_score < 1.0
    assert "large_debit_ids" in result.field_errors[0]


def test_extra_account() -> None:
    data = _b()
    data["accounts"].append(
        {
            "account_id": "ACC-0010-3",
            "available_balance": 1.0,
            "spend_by_category": {},
            "large_debit_ids": [],
        }
    )
    result = _score_b(data)
    assert result.outcome == "incorrect"
    assert result.partial_score < 1.0
    assert "ACC-0010-3" in result.field_errors[0]


@pytest.mark.parametrize(
    "text",
    ["garbage", "[1, 2, 3]", '{"account_id": "ACC-0050-1"}', '{"account_id": 5, "x": 1}'],
)
def test_invalid_answers(text: str) -> None:
    for result in (score_answer_a(EXPECTED_A, text), score_answer_b(EXPECTED_B, text)):
        assert result.outcome == "invalid_answer"
        assert result.partial_score == 0.0
        assert len(result.field_errors) == 1


EXPECTED_C = AnswerC(
    customer_id="CUST-0100",
    top_merchants=[
        MerchantTotal(merchant="Beta", total=150.00),
        MerchantTotal(merchant="Gamma", total=100.01),
        MerchantTotal(merchant="Alpha", total=30.01),
    ],
    weekend_debit_count=3,
)


def _c(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXPECTED_C.model_dump_json())
    data.update(changes)
    return data


def _score_c(data: Any) -> Any:
    return score_answer_c(EXPECTED_C, json.dumps(data))


def test_c_exact_answer_correct() -> None:
    result = _score_c(_c())
    assert (result.outcome, result.partial_score, result.field_errors) == ("correct", 1.0, ())


def test_c_tolerance_whitespace_and_extras() -> None:
    merchants = [
        {"merchant": " Beta ", "total": 150.0049},
        {"merchant": "Gamma", "total": 100.02},
        {"merchant": "Alpha", "total": 30.01},
        {"merchant": "Delta", "total": 1.0},  # a fourth entry is ignored
    ]
    assert _score_c(_c(top_merchants=merchants, extra="x")).outcome == "correct"


def test_c_each_wrong_field_costs_one_of_eight() -> None:
    cases = {
        "customer_id": _c(customer_id="CUST-0050"),
        "weekend_debit_count": _c(weekend_debit_count=4),
        "merchant name": _c(
            top_merchants=[
                {"merchant": "beta", "total": 150.0},  # case-sensitive
                *_c()["top_merchants"][1:],
            ]
        ),
        "total": _c(
            top_merchants=[
                {"merchant": "Beta", "total": 150.02},  # beyond +-0.01
                *_c()["top_merchants"][1:],
            ]
        ),
    }
    for name, data in cases.items():
        result = _score_c(data)
        assert result.outcome == "incorrect", name
        assert result.partial_score == pytest.approx(7 / 8), name
        assert len(result.field_errors) == 1, name


def test_c_wrong_order_and_missing_ranks() -> None:
    swapped = _c(top_merchants=list(reversed(_c()["top_merchants"])))
    result = _score_c(swapped)
    assert result.outcome == "incorrect"
    assert result.partial_score == pytest.approx(4 / 8)  # rank 2 happens to match, 1 and 3 not
    short = _score_c(_c(top_merchants=_c()["top_merchants"][:1]))
    assert short.outcome == "incorrect"
    assert short.partial_score == pytest.approx(4 / 8)
    none = _score_c(_c(top_merchants=[]))
    assert none.partial_score == pytest.approx(2 / 8)


def test_c_invalid_answers() -> None:
    assert score_answer_c(EXPECTED_C, "no json here").outcome == "invalid_answer"
    missing = _c()
    del missing["weekend_debit_count"]
    result = _score_c(missing)
    assert result.outcome == "invalid_answer"
    assert result.partial_score == 0.0
