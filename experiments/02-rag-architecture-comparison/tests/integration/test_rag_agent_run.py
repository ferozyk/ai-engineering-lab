"""End-to-end agentic runs with the fake chat model (no model, no network, no API key)."""

import csv
import json
import shutil
from collections.abc import Collection
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest

from rag_experiment import answer_commands, cli
from rag_experiment.agent.fake import FakeAgentChatModel
from rag_experiment.config import ExperimentConfig, RunConfig
from rag_experiment.evaluation.answer_analysis import AnswerSummary
from rag_experiment.evaluation.answer_run import (
    AnswerRecord,
    AnswerRunMetadata,
    RunPaths,
    load_records,
    plan_attempts,
)
from rag_experiment.evaluation.dataset import load_questions

pytestmark = pytest.mark.integration


@pytest.fixture
def results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> Path:
    """Redirect results to a temp folder and make sure fake runs never build a client."""
    root = tmp_path / "results"
    monkeypatch.setattr(cli, "_results_root_base", lambda config: root)

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a network client was constructed in a fake run")

    monkeypatch.setattr(openai, "AsyncOpenAI", refuse)
    monkeypatch.setattr(answer_commands, "AsyncOpenAI", refuse)
    monkeypatch.setattr(httpx, "AsyncClient", refuse)
    monkeypatch.setattr(
        cli, "_settings", lambda config: pytest.fail("settings were read in a fake run")
    )
    return root


def _only_run(root: Path) -> RunPaths:
    runs = list((root / "dry-run" / "raw").iterdir())
    assert len(runs) == 1
    return RunPaths(root / "dry-run", runs[0].name)


def _metadata(paths: RunPaths) -> AnswerRunMetadata:
    return AnswerRunMetadata.model_validate_json(paths.metadata.read_text(encoding="utf-8"))


def _summary(paths: RunPaths) -> AnswerSummary:
    return AnswerSummary.model_validate_json(
        (paths.processed / "answer_summary.json").read_text(encoding="utf-8")
    )


def _knobs(monkeypatch: pytest.MonkeyPatch, *, infra: Collection[str] = ()) -> None:
    def build(questions: Any, chunks: Any, **kwargs: Any) -> FakeAgentChatModel:
        return FakeAgentChatModel(questions, chunks, infra_error_for=infra, **kwargs)

    monkeypatch.setattr(answer_commands, "FakeAgentChatModel", build)


def test_measured_agentic_fake_run_end_to_end(
    results: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run", "--set", "measured", "--retriever", "agentic", "--fake"]) == 0
    out = capsys.readouterr().out
    assert "SIMULATED" in out and " calls=" in out and " searches=" in out
    assert "HD1: not applicable (simulated)" in out and "architecture B: 3/12" in out
    assert not (results / "raw").exists() and not (results / "processed").exists()
    paths = _only_run(results)
    assert paths.run_id.endswith("-answers-measured-agentic-fake")

    records = load_records(paths.answers)
    assert len(records) == 120 == len({r.attempt_id for r in records})
    assert all(r.agentic and r.simulated and r.rerank_ms == 0.0 for r in records)
    assert all(3 <= r.model_calls <= 5 and 1 <= r.searches <= 3 for r in records)
    assert all(r.calls is not None and len(r.calls) == r.model_calls for r in records)
    assert all(r.calls and r.calls[0].step == "plan" for r in records)
    assert all(r.calls and r.calls[-1].step == "answer" for r in records)
    assert all(len(r.context_chunk_ids) <= 10 for r in records)
    assert all(len(r.queries) == r.searches for r in records)
    assert all(r.attempts == r.model_calls for r in records)  # one request per call
    assert all(
        r.total_ms == pytest.approx(r.embed_ms + r.search_ms + r.agent_ms + r.generation_ms)
        for r in records
    )
    assert all(r.n_sources == 0 for r in records if r.must_abstain)
    raw_rows = [json.loads(line) for line in paths.answers.read_text("utf-8").splitlines()]
    assert all("calls" in row and "queries" in row and "rerank_ms" not in row for row in raw_rows)
    assert {r.outcome for r in records if r.must_abstain} == {"refused"}

    meta = _metadata(paths)
    assert meta.retriever == "agentic" and meta.simulated and not meta.halted
    assert meta.agent is not None and meta.agent["max_searches"] == 3
    assert meta.agent["prompt_version"] == "d-1.0" and len(str(meta.agent["prompt_hash"])) == 64
    assert meta.agent["search_tool"] == {
        "retriever": "hybrid",
        "bm25_k1": 1.2,
        "bm25_b": 0.75,
        "rrf_k": 60,
        "candidate_depth": 50,
    }
    assert meta.prompt_version == "a-1.0" and "langgraph" in meta.package_versions
    assert meta.requests_sent == sum(r.attempts for r in records)
    assert meta.failed_requests == 0 and meta.attempts_completed == 120

    summary = _summary(paths)
    assert summary.agent is not None and summary.agent.n_attempts == 120
    assert [v.hypothesis for v in summary.verdicts] == ["HD1", "HD2", "HD3"]
    assert {v.verdict for v in summary.verdicts} == {"not applicable (simulated)"}
    assert [*summary.latency_ms] == ["embed", "search", "agent", "generation", "total"]
    assert summary.requests.sent == meta.requests_sent and summary.requests.failed == 0

    report = (paths.reports / "answer_report.md").read_text("utf-8")
    assert "## Agent behaviour" in report and "SIMULATED" in report
    assert "Queries run in repetition 1 for each multi_endpoint question" in report
    assert "no Hit@K chart" not in report  # a console note only
    assert not (paths.charts / "retrieval_hit_at_k.png").exists()
    assert (paths.charts / "latency_by_stage.png").is_file()
    with (paths.processed / "answers_by_attempt.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 120 and {"agent_ms", "model_calls", "searches"} <= set(rows[0])

    transcript = json.loads(
        (paths.transcripts / f"{records[0].attempt_id}.json").read_text("utf-8")
    )
    assert "messages" not in transcript
    assert transcript["steps"][0]["step"] == "plan"
    assert transcript["steps"][-1]["step"] == "answer"
    assert all({"messages", "raw_content"} <= set(s) for s in transcript["steps"])
    assert len(transcript["searches"]) == records[0].searches
    assert "Authorization" not in json.dumps(transcript)


def test_agentic_canary_runs_three_questions_once(results: Path) -> None:
    assert cli.main(["canary", "--retriever", "agentic", "--fake"]) == 0
    paths = _only_run(results)
    assert paths.run_id.endswith("-answers-dev-agentic-canary-fake")
    records = load_records(paths.answers)
    assert sorted(r.question_id for r in records) == ["Q01", "Q05", "Q14"]
    assert {r.repetition for r in records} == {1} and all(r.agentic for r in records)
    meta = _metadata(paths)
    assert meta.is_canary and meta.attempts_planned == 3 and meta.agent is not None


def test_analyse_reproduces_an_agentic_summary_and_report(
    results: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["canary", "--retriever", "agentic", "--fake"]) == 0
    paths = _only_run(results)
    before = (paths.processed / "answer_summary.json").read_text("utf-8")
    report = (paths.reports / "answer_report.md").read_text("utf-8")
    shutil.rmtree(paths.processed)
    shutil.rmtree(paths.reports)
    capsys.readouterr()
    assert cli.main(["analyse", paths.run_id]) == 0
    assert (paths.processed / "answer_summary.json").read_text("utf-8") == before
    assert (paths.reports / "answer_report.md").read_text("utf-8") == report


def test_an_infrastructure_error_in_the_first_call_is_recorded_and_the_run_continues(
    results: Path, monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> None:
    plan = plan_attempts(
        load_questions(experiment_config.questions_dev), 1, experiment_config.run.order_seed
    )
    victim = plan[3].attempt_id
    _knobs(monkeypatch, infra={victim})
    assert cli.main(["run", "--set", "dev", "--retriever", "agentic", "--fake"]) == 0
    paths = _only_run(results)
    latest = {r.attempt_id: r for r in load_records(paths.answers)}
    bad = latest[victim]
    assert bad.outcome == "infra_error" and bad.error_kind == "server"
    assert bad.calls == () and bad.model_calls == 0 and bad.attempts == 1
    assert bad.searches == 0 and bad.queries == ()
    assert sum(1 for r in latest.values() if r.outcome == "infra_error") == 1
    meta = _metadata(paths)
    assert meta.infra_errors == 1 and meta.failed_requests == 1
    assert meta.requests_sent == sum(r.attempts for r in load_records(paths.answers))


def test_a_budget_halt_mid_attempt_drops_that_attempt_and_resume_completes_the_run(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    experiment_config: ExperimentConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capped = experiment_config.model_copy(
        update={"run": RunConfig(**{**experiment_config.run.model_dump(), "daily_request_cap": 10})}
    )
    monkeypatch.setattr(cli, "load_config", lambda path: capped)
    assert cli.main(["run", "--set", "dev", "--retriever", "agentic", "--fake"]) == 1
    out = capsys.readouterr().out
    assert "HALTED" in out and "--resume" in out
    paths = _only_run(results)
    first = load_records(paths.answers)
    meta = _metadata(paths)
    assert meta.halted and "daily request cap" in (meta.halt_reason or "")
    assert 0 < len(first) < 45
    # the cap counts requests: the attempt that hit it was not recorded, so it is redone
    assert sum(r.attempts for r in first) <= 10

    monkeypatch.setattr(cli, "load_config", lambda path: experiment_config)
    args = ["run", "--set", "dev", "--retriever", "agentic", "--fake", "--resume", paths.run_id]
    assert cli.main(args) == 0
    records = load_records(paths.answers)
    assert len(records) == len({r.attempt_id for r in records}) == 45
    meta = _metadata(paths)
    assert not meta.halted and meta.attempts_completed == 45
    assert meta.requests_sent == sum(r.attempts for r in records)
    assert len(list((results / "dry-run" / "raw").iterdir())) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["evaluate-retrieval", "--set", "dev", "--retriever", "agentic", "--fake-embeddings"],
        ["retrieve", "some question", "--retriever", "agentic", "--fake-embeddings"],
    ],
)
def test_retrieval_commands_reject_the_agentic_retriever(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    assert "agentic retrieval needs the model; its retrieval is measured inside the answer run" in (
        captured.err
    )
    assert captured.out == ""


def test_records_of_other_retrievers_carry_no_agent_keys(results: Path) -> None:
    assert cli.main(["canary", "--fake"]) == 0
    paths = _only_run(results)
    row = json.loads(paths.answers.read_text("utf-8").splitlines()[0])
    assert not {"calls", "model_calls", "searches", "queries", "agent_ms", "n_sources"} & set(row)
    meta = json.loads(paths.metadata.read_text("utf-8"))
    assert "agent" not in meta and "langgraph" not in meta["package_versions"]
    summary = json.loads((paths.processed / "answer_summary.json").read_text("utf-8"))
    assert "agent" not in summary and "agent" not in summary["latency_ms"]
    header = (paths.processed / "answers_by_attempt.csv").read_text("utf-8").splitlines()[0]
    assert "model_calls" not in header and "agent_ms" not in header
    assert isinstance(load_records(paths.answers)[0], AnswerRecord)
