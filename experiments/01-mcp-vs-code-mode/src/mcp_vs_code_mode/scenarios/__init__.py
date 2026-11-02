"""Scenario definitions, ground truth and scoring."""

from mcp_vs_code_mode.scenarios.definitions import (
    SCENARIO_A_ACCOUNT_ID,
    AccountSummary,
    AnswerA,
    AnswerB,
    AnswerC,
    MerchantTotal,
    ScenarioId,
    TaskSpec,
    scenario_a_task,
    scenario_b_task,
    scenario_c_task,
)
from mcp_vs_code_mode.scenarios.ground_truth import (
    expected_answer_a,
    expected_answer_b,
    expected_answer_c,
)
from mcp_vs_code_mode.scenarios.scoring import (
    Outcome,
    ScoreResult,
    extract_json_object,
    score_answer_a,
    score_answer_b,
    score_answer_c,
)

__all__ = [
    "SCENARIO_A_ACCOUNT_ID",
    "AccountSummary",
    "AnswerA",
    "AnswerB",
    "AnswerC",
    "MerchantTotal",
    "Outcome",
    "ScenarioId",
    "ScoreResult",
    "TaskSpec",
    "expected_answer_a",
    "expected_answer_b",
    "expected_answer_c",
    "extract_json_object",
    "scenario_a_task",
    "scenario_b_task",
    "scenario_c_task",
    "score_answer_a",
    "score_answer_b",
    "score_answer_c",
]
