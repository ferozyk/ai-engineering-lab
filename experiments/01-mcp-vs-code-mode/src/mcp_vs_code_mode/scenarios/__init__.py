"""Scenario definitions, ground truth and scoring."""

from mcp_vs_code_mode.scenarios.definitions import (
    SCENARIO_A_ACCOUNT_ID,
    AccountSummary,
    AnswerA,
    AnswerB,
    ScenarioId,
    TaskSpec,
    scenario_a_task,
    scenario_b_task,
)
from mcp_vs_code_mode.scenarios.ground_truth import expected_answer_a, expected_answer_b
from mcp_vs_code_mode.scenarios.scoring import (
    Outcome,
    ScoreResult,
    extract_json_object,
    score_answer_a,
    score_answer_b,
)

__all__ = [
    "SCENARIO_A_ACCOUNT_ID",
    "AccountSummary",
    "AnswerA",
    "AnswerB",
    "Outcome",
    "ScenarioId",
    "ScoreResult",
    "TaskSpec",
    "expected_answer_a",
    "expected_answer_b",
    "extract_json_object",
    "scenario_a_task",
    "scenario_b_task",
    "score_answer_a",
    "score_answer_b",
]
