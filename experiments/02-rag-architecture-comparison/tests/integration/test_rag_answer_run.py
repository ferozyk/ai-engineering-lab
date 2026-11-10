"""End-to-end answer runs with the fake chat model (no model, no network, no API key)."""

import json
import shutil
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest

from ai_lab.config import load_settings
from ai_lab.llm import InfraErrorKind
from rag_experiment import answer_commands, cli
from rag_experiment.config import ExperimentConfig, RunConfig
from rag_experiment.evaluation import retrieval_run
from rag_experiment.evaluation.answer_analysis import AnswerSummary
from rag_experiment.evaluation.answer_run import (
    AnswerRunMetadata,
    RunPaths,
    load_records,
    plan_attempts,
)
from rag_experiment.evaluation.dataset import load_questions
from rag_experiment.generation.fake import FakeChatModel

pytestmark = pytest.mark.integration

EXP_ROOT = Path(__file__).resolve().parents[2]
SECRET = "secret-key-value-123"


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


def _set_config(monkeypatch: pytest.MonkeyPatch, config: ExperimentConfig, **run: int) -> None:
    changed = config.model_copy(update={"run": RunConfig(**{**config.run.model_dump(), **run})})
    monkeypatch.setattr(cli, "load_config", lambda path: changed)


def _knobs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    infra: Collection[str] = (),
    kind: InfraErrorKind = "server",
    invalid: Collection[str] = (),
    cut_off: Collection[str] = (),
) -> None:
    def build(questions: Any, chunks: Any, **kwargs: Any) -> FakeChatModel:
        return FakeChatModel(
            questions,
            chunks,
            infra_error_for=infra,
            infra_error_kind=kind,
            invalid_json_for=invalid,
            cut_off_for=cut_off,
            **kwargs,
        )

    monkeypatch.setattr(answer_commands, "FakeChatModel", build)


def test_dev_fake_run_end_to_end(
    results: Path, experiment_config: ExperimentConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run", "--set", "dev", "--fake"]) == 0
    out = capsys.readouterr().out
    assert "SIMULATED" in out and "not applicable (simulated)" in out

    assert not (results / "raw").exists()
    assert not (results / "processed").exists()
    assert not (results / "reports").exists()
    assert not (results / "charts").exists()
    paths = _only_run(results)
    assert paths.run_id.endswith("-answers-dev-dense-fake")
    for name in ("run_metadata.json", "answers.jsonl"):
        assert (paths.raw / name).is_file()
    assert len(list(paths.transcripts.glob("*.json"))) == 45
    assert (paths.processed / "answer_summary.json").is_file()
    assert (paths.processed / "answers_by_attempt.csv").is_file()
    assert len((paths.processed / "answers_by_attempt.csv").read_text("utf-8").splitlines()) == 46
    report = (paths.reports / "answer_report.md").read_text("utf-8")
    assert "SIMULATED" in report and "Author interpretation: see the experiment README" in report
    pngs = {p.name for p in paths.charts.glob("*.png")}
    assert {"ha3_correctness_by_context.png", "guardrails.png", "latency_by_stage.png"} <= pngs
    assert {"tokens_per_question.png"} <= pngs and len(list(paths.charts.glob("*.svg"))) >= 4

    records = load_records(paths.answers)
    assert len(records) == 45 == len({r.attempt_id for r in records})
    assert all(r.simulated and r.provider == "simulated" for r in records)
    answerable = [r for r in records if not r.must_abstain]
    hits = [r for r in answerable if r.context_hit]
    assert hits and all(r.correct is True and r.outcome == "answered" for r in hits)
    assert all(r.outcome == "refused" and r.false_refusal for r in answerable if not r.context_hit)
    unanswerable = [r for r in records if r.must_abstain]
    assert len(unanswerable) == 6 and all(r.correct_refusal is True for r in unanswerable)
    assert all(r.context_chunk_ids and len(r.context_chunk_ids) == 5 for r in records)
    assert all(
        r.total_ms == pytest.approx(r.embed_ms + r.search_ms + r.generation_ms) for r in records
    )

    meta = _metadata(paths)
    assert meta.simulated and meta.kind == "answers" and meta.provider == "simulated"
    assert meta.prompt_version == "a-1.0" and len(meta.prompt_hash) == 64
    assert meta.attempts_planned == meta.attempts_completed == 45
    assert meta.requests_sent == 45 and meta.failed_requests == 0 and not meta.halted
    assert meta.free_model_daily_requests_before is None
    assert {"openai", "httpx", "matplotlib"} <= set(meta.package_versions)
    assert meta.pricing.source == "simulated" and meta.question_set == "dev"
    summary = _summary(paths)
    assert summary.simulated and summary.n_scored == 45
    assert {v.verdict for v in summary.verdicts} == {"not applicable (simulated)"}

    # a transcript holds the prompt and reply, and nothing about the request or credentials
    transcript = json.loads((paths.transcripts / "Q01-r1.json").read_text("utf-8"))
    assert set(transcript) == {
        "run_id",
        "attempt_id",
        "question_id",
        "repetition",
        "simulated",
        "messages",
        "raw_content",
        "parsed",
        "outcome",
        "error_kind",
        "error_message",
    }
    assert [m["role"] for m in transcript["messages"]] == ["system", "user"]


def test_canary_fake_runs_three_questions_once(results: Path) -> None:
    assert cli.main(["canary", "--fake"]) == 0
    paths = _only_run(results)
    assert paths.run_id.endswith("-canary-fake")
    records = load_records(paths.answers)
    assert sorted(r.question_id for r in records) == ["Q01", "Q05", "Q14"]
    assert {r.repetition for r in records} == {1}
    meta = _metadata(paths)
    assert (
        meta.is_canary and meta.attempts_planned == 3 and meta.question_ids == ["Q01", "Q05", "Q14"]
    )


def test_git_state_is_captured_at_start_not_at_the_end(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editing the working tree during a run must not change the recorded commit state."""
    monkeypatch.setattr(answer_commands, "git_state", lambda root: ("start-sha", False))
    monkeypatch.setattr(retrieval_run, "git_state", lambda root: ("later-sha", True))
    assert cli.main(["canary", "--fake"]) == 0
    meta = _metadata(_only_run(results))
    assert (meta.git_sha, meta.git_dirty) == ("start-sha", False)


def test_measured_fake_run_has_120_records_and_no_verdicts(results: Path) -> None:
    assert cli.main(["run", "--set", "measured", "--fake"]) == 0
    paths = _only_run(results)
    records = load_records(paths.answers)
    assert len(records) == 120 and len({r.attempt_id for r in records}) == 120
    summary = _summary(paths)
    assert {v.verdict for v in summary.verdicts} == {"not applicable (simulated)"}
    assert _metadata(paths).question_set == "measured"
    assert (paths.reports / "answer_report.md").read_text("utf-8").count("SIMULATED") >= 1


def test_every_outcome_path_is_scored(
    results: Path, monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> None:
    plan3 = plan_attempts(
        load_questions(experiment_config.questions_dev), 3, experiment_config.run.order_seed
    )
    ids = [p.attempt_id for p in plan3]
    _knobs(monkeypatch, invalid={ids[0]}, cut_off={ids[1]}, infra={ids[2]})
    assert cli.main(["run", "--set", "dev", "--fake"]) == 0
    runs = sorted((results / "dry-run" / "raw").iterdir())
    paths = RunPaths(results / "dry-run", runs[-1].name)
    latest = {r.attempt_id: r for r in load_records(paths.answers)}
    assert latest[ids[0]].outcome == "invalid_answer" and latest[ids[0]].parse_error
    assert latest[ids[1]].outcome == "cut_off" and latest[ids[1]].finish_reason == "length"
    assert latest[ids[2]].outcome == "infra_error" and latest[ids[2]].error_kind == "server"
    summary = _summary(paths)
    assert summary.n_infra_errors == 1 and summary.n_scored == 44
    assert (
        summary.overall.outcomes["invalid_answer"] == 1 and summary.overall.outcomes["cut_off"] == 1
    )


def test_resume_after_a_budget_halt_completes_without_duplicate_successes(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    experiment_config: ExperimentConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = plan_attempts(
        load_questions(experiment_config.questions_dev), 3, experiment_config.run.order_seed
    )
    early = {plan[0].attempt_id, plan[1].attempt_id, plan[2].attempt_id}
    _knobs(monkeypatch, infra=early)
    _set_config(monkeypatch, experiment_config, daily_request_cap=20)
    assert cli.main(["run", "--set", "dev", "--fake"]) == 1
    out = capsys.readouterr().out
    assert "HALTED" in out and "--resume" in out
    paths = _only_run(results)
    first = load_records(paths.answers)
    assert len(first) == 20
    meta = _metadata(paths)
    assert meta.halted and "daily request cap" in (meta.halt_reason or "")
    assert meta.attempts_completed == 17 and meta.infra_errors == 3
    assert (paths.reports / "answer_report.md").is_file()  # partial outputs are still written

    # resume with a normal config and no faults
    _knobs(monkeypatch)
    monkeypatch.setattr(cli, "load_config", lambda path: experiment_config)
    assert cli.main(["run", "--set", "dev", "--fake", "--resume", paths.run_id]) == 0
    records = load_records(paths.answers)
    assert len(records) == 20 + 28 == 48
    assert len({r.attempt_id for r in records}) == 45
    successes = [r for r in records if r.outcome != "infra_error"]
    assert len(successes) == 45 == len({r.attempt_id for r in successes})
    assert len([r for r in records if r.outcome == "infra_error"]) == 3
    meta = _metadata(paths)
    assert not meta.halted and meta.attempts_completed == 45 and meta.infra_errors == 3
    assert meta.requests_sent == 48 and meta.failed_requests == 3
    assert _summary(paths).n_scored == 45 and _summary(paths).n_infra_errors == 0
    # still only one run directory: the resume appended to the same run
    assert len(list((results / "dry-run" / "raw").iterdir())) == 1


def test_daily_limit_halts_cleanly(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    experiment_config: ExperimentConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = plan_attempts(
        load_questions(experiment_config.questions_dev), 3, experiment_config.run.order_seed
    )
    _knobs(monkeypatch, infra={plan[4].attempt_id}, kind="daily_limit")
    assert cli.main(["run", "--set", "dev", "--fake"]) == 1
    assert "HALTED" in capsys.readouterr().out
    paths = _only_run(results)
    records = load_records(paths.answers)
    assert len(records) == 5 and records[-1].outcome == "infra_error"
    assert records[-1].error_kind == "daily_limit"
    meta = _metadata(paths)
    assert meta.halted and "daily_limit" in (meta.halt_reason or "")
    assert meta.attempts_completed == 4 and meta.attempts_planned == 45


def test_five_consecutive_infrastructure_errors_halt(
    results: Path, monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> None:
    plan = plan_attempts(
        load_questions(experiment_config.questions_dev), 3, experiment_config.run.order_seed
    )
    _knobs(monkeypatch, infra={p.attempt_id for p in plan[2:9]})
    assert cli.main(["run", "--set", "dev", "--fake"]) == 1
    paths = _only_run(results)
    assert len(load_records(paths.answers)) == 7  # 2 good + 5 consecutive failures
    assert "consecutive" in (_metadata(paths).halt_reason or "")


def test_keyboard_interrupt_finalises_the_run(
    results: Path, monkeypatch: pytest.MonkeyPatch, experiment_config: ExperimentConfig
) -> None:
    class Interrupting(FakeChatModel):
        async def complete(self, messages: Any, tools: Any = ()) -> Any:
            if self.calls == 3:
                raise KeyboardInterrupt
            return await super().complete(messages, tools)

    monkeypatch.setattr(answer_commands, "FakeChatModel", Interrupting)
    assert cli.main(["run", "--set", "dev", "--fake"]) == 1
    paths = _only_run(results)
    assert len(load_records(paths.answers)) == 3
    meta = _metadata(paths)
    assert meta.halted and "interrupted" in (meta.halt_reason or "")
    assert (paths.reports / "answer_report.md").is_file()


def test_analyse_reproduces_the_summary(results: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "--set", "dev", "--fake"]) == 0
    paths = _only_run(results)
    summary_path = paths.processed / "answer_summary.json"
    before = summary_path.read_text("utf-8")
    report_before = (paths.reports / "answer_report.md").read_text("utf-8")
    shutil.rmtree(paths.processed)
    shutil.rmtree(paths.charts)
    shutil.rmtree(paths.reports)
    capsys.readouterr()
    assert cli.main(["analyse", paths.run_id]) == 0
    assert summary_path.read_text("utf-8") == before
    assert (paths.reports / "answer_report.md").read_text("utf-8") == report_before
    assert (paths.charts / "guardrails.png").is_file()
    assert cli.main(["analyse", "no-such-run"]) == 2


def test_hit_at_k_chart_uses_a_committed_retrieval_run(results: Path) -> None:
    source = EXP_ROOT / "results"
    run_id = answer_commands.find_retrieval_run(source, "dev")
    assert run_id is not None
    for part in ("raw", "processed"):
        shutil.copytree(source / part / run_id, results / part / run_id)
    assert cli.main(["run", "--set", "dev", "--fake", "--retrieval-run", run_id]) == 0
    paths = _only_run(results)
    assert (paths.charts / "retrieval_hit_at_k.png").is_file()


# ---------------------------------------------------------------- preflight and credentials


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def configure(*, key: bool, model: bool) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        if key:
            monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
        if model:
            monkeypatch.setenv("LLM_MODEL", "test/model")
        monkeypatch.setattr(cli, "_settings", lambda config: load_settings(env_file=None))
        monkeypatch.setattr(
            answer_commands,
            "index_status",
            lambda *a, **k: answer_commands.CheckResult("index", "pass", "ok"),
        )

    return configure


def test_preflight_offline_exit_codes_and_no_secret_in_output(
    settings_env: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env(key=True, model=True)
    assert cli.main(["preflight"]) == 0
    out = capsys.readouterr()
    assert "OPENROUTER_API_KEY is set" in out.out and "test/model" in out.out
    assert SECRET not in out.out + out.err
    assert "live checks" not in out.out

    settings_env(key=False, model=True)
    assert cli.main(["preflight"]) == 1
    out = capsys.readouterr()
    assert "OPENROUTER_API_KEY is not set" in out.out and SECRET not in out.out + out.err

    settings_env(key=True, model=False)
    assert cli.main(["preflight"]) == 1
    assert "LLM_MODEL is not set" in capsys.readouterr().out


def test_real_run_without_credentials_exits_2_with_a_message(
    settings_env: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env(key=False, model=False)
    assert cli.main(["run", "--set", "dev"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("Error:") and "LLM_MODEL" in err and "Traceback" not in err
    settings_env(key=False, model=True)
    assert cli.main(["canary"]) == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_resume_refuses_a_different_kind_of_run(
    results: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run", "--set", "dev", "--fake"]) == 0
    paths = _only_run(results)
    assert cli.main(["run", "--set", "measured", "--fake", "--resume", paths.run_id]) == 2
    assert "dev" in capsys.readouterr().err
