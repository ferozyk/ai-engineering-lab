"""The answer report (Markdown) and the per-attempt CSV. They state measurements, not opinions."""

import csv
from collections.abc import Sequence
from pathlib import Path

from rag_experiment.evaluation.answer_analysis import AnswerGroup, AnswerSummary
from rag_experiment.evaluation.answer_run import (
    AnswerRecord,
    AnswerRunMetadata,
    latest_by_attempt,
    write_json,
)
from rag_experiment.evaluation.retrieval_metrics import RatioValue

# Copied from docs/evaluation-methodology.md section 9 (a test checks they still match).
LIMITATIONS = (
    "Small, synthetic, self-authored corpus and question set.",
    "A single generation model.",
    "Qdrant local-mode latency does not represent a Qdrant server.",
    "Free-model routing variance on OpenRouter.",
    "Deterministic groundedness covers identifiers only.",
    "BGE-M3 is larger than an English corpus of this size needs.",
    "The sample size is small, so results are per-question rather than statistically significant.",
)
BANNER = (
    "> SIMULATED run: the model is a deterministic fake (an oracle with injected faults), "
    "not a language model. Nothing in this report is a measurement."
)


def _ratio(value: RatioValue) -> str:
    if value.value is None:
        return "n/a (0)"
    return f"{value.numerator}/{value.denominator} = {value.value:.3f}"


def _results_table(summary: AnswerSummary) -> list[str]:
    header = (
        "| group | n | answered | refused | invalid | cut off | correctness (answerable) "
        "| false refusal (answerable) | correct refusal (unanswerable) |"
    )
    lines = [header, "|" + "---|" * 9]
    groups: list[tuple[str, AnswerGroup]] = [("overall", summary.overall)]
    groups.extend(summary.by_category.items())
    for name, g in groups:
        o = g.outcomes
        lines.append(
            f"| {name} | {g.n} | {o.get('answered', 0)} | {o.get('refused', 0)} | "
            f"{o.get('invalid_answer', 0)} | {o.get('cut_off', 0)} | {_ratio(g.answerable)} | "
            f"{_ratio(g.false_refusals)} | {_ratio(g.correct_refusals)} |"
        )
    return lines


def render_answer_report(
    metadata: AnswerRunMetadata,
    summary: AnswerSummary,
    chart_files: Sequence[str] = (),
) -> str:
    """The generated Markdown report. It does not interpret the numbers."""
    emb = metadata.embedding
    out: list[str] = [f"# Answer report: {metadata.run_id}", ""]
    if summary.simulated:
        out += [BANNER, ""]
    out += [
        "## Setup",
        "",
        f"- Corpus: version {metadata.corpus_version}, checksum `{metadata.corpus_checksum}`",
        f"- Question set: {metadata.question_set}, version {metadata.question_set_version}, "
        f"checksum `{metadata.question_set_checksum}`"
        + (f"; canary subset {', '.join(metadata.question_ids)}" if metadata.is_canary else ""),
        f"- Generation model: `{metadata.model_id}` via {metadata.provider}; "
        f"served by models {metadata.models_served or 'n/a'}, providers "
        f"{metadata.providers_served or 'n/a'}",
        f"- Prompt: version {metadata.prompt_version}, hash `{metadata.prompt_hash}`",
        f"- Generation settings: {metadata.generation}",
        f"- Run settings: {metadata.run}",
        f"- Retrieval: {metadata.retriever}, context = top {metadata.retrieval['top_k_generation']}"
        f" chunks; embedding `{emb.model_id}` revision `{emb.revision}` ({emb.device}); "
        f"collection `{metadata.collection}`; retrieval deterministic: {metadata.deterministic}",
        f"- Run timing: started {metadata.started_at:%Y-%m-%d %H:%M:%S} UTC, "
        f"finished {metadata.finished_at:%Y-%m-%d %H:%M:%S} UTC",
        f"- Git: `{metadata.git_sha}` (dirty: {metadata.git_dirty}); "
        f"Python {metadata.python_version}; {metadata.os}",
        f"- Attempts: {metadata.attempts_planned} planned, "
        f"{metadata.attempts_completed} completed, "
        f"{summary.n_infra_errors} unresolved infrastructure errors; "
        f"halted: {metadata.halted}"
        + (f" ({metadata.halt_reason})" if metadata.halt_reason else ""),
        "",
        "## Results",
        "",
        "Infrastructure errors are excluded from every quality denominator below.",
        "",
        *_results_table(summary),
        "",
        "## Hypotheses (frozen criteria, computed mechanically)",
        "",
        "| hypothesis | criterion | verdict | evidence |",
        "|---|---|---|---|",
    ]
    for v in summary.verdicts:
        out.append(f"| {v.hypothesis} | {v.criterion} | {v.verdict} | {v.evidence} |")
    g = summary.guardrails
    out += [
        "",
        "## Guardrails",
        "",
        "| measure | value |",
        "|---|---|",
        f"| correct refusal (unanswerable) | {_ratio(g.correct_refusal)} |",
        f"| made-up answer (unanswerable) | {_ratio(g.made_up_answer)} |",
        f"| invalid answers on unanswerable attempts | {g.unanswerable_invalid} |",
        f"| cut-off answers on unanswerable attempts | {g.unanswerable_cut_off} |",
        f"| false refusal (answerable) | {_ratio(g.false_refusal)} |",
        f"| diagnostic: unanswerable answers naming an endpoint (not scored) | "
        f"{g.mentions_endpoint_on_unanswerable} |",
        "",
        "## Groundedness and citations",
        "",
        "Identifiers only (endpoints, paths, error codes, scopes, headers, names); "
        "identifiers repeated from the question are not counted.",
        "",
        "| measure | value |",
        "|---|---|",
        f"| answers with at least one unsupported identifier | "
        f"{_ratio(summary.groundedness.with_unsupported)} |",
        f"| answers with at least one invented identifier | "
        f"{_ratio(summary.groundedness.with_invented)} |",
        f"| all cited ids were in the context (answered, must cite) | "
        f"{_ratio(summary.citations.citations_valid)} |",
        f"| at least one cited id is relevant (answered, must cite) | "
        f"{_ratio(summary.citations.cites_relevant)} |",
        "",
        "Most frequent unsupported identifiers: "
        + (", ".join(f"`{i}` x{n}" for i, n in summary.groundedness.top_unsupported) or "none"),
        "",
        "Most frequent invented identifiers: "
        + (", ".join(f"`{i}` x{n}" for i, n in summary.groundedness.top_invented) or "none"),
        "",
        "## Per question",
        "",
        "| id | category | context hit | correct | outcomes | agree | missing key facts |",
        "|---|---|---|---|---|---|---|",
    ]
    for q in summary.per_question:
        out.append(
            f"| {q.question_id} | {q.category} | {'yes' if q.context_hit else 'no'} | "
            f"{q.correct}/{q.attempts} | {', '.join(q.outcomes)} | "
            f"{'yes' if q.repetitions_agree else 'no'} | "
            f"{', '.join(f'`{f}`' for f in q.missing_key_facts) or '-'} |"
        )
    out += [
        "",
        "For an unanswerable question 'correct' counts correct refusals.",
        "",
        "## Latency",
        "",
        "Qdrant local mode, in-process, exact search; CPU. Total = embed + search + generation, "
        "without client-side throttling. With few attempts p95 rests on a handful of "
        "observations.",
        "",
        "| stage | n | p50 (ms) | p95 (ms) |",
        "|---|---|---|---|",
    ]
    for name, lat in summary.latency_ms.items():
        out.append(f"| {name} | {lat.n} | {lat.p50:.2f} | {lat.p95:.2f} |")
    out += [
        "",
        "## Tokens and cost (estimated)",
        "",
        "Tokens as reported by the provider.",
        "",
        "| tokens | n | mean | p50 | p95 |",
        "|---|---|---|---|---|",
    ]
    for name, t in summary.tokens.items():
        out.append(f"| {name} | {t.n} | {t.mean:.1f} | {t.p50:.1f} | {t.p95:.1f} |")
    c = summary.cost
    r = summary.requests
    out += [
        "",
        f"- Estimated cost per 1,000 questions: ${c.per_1000_questions_usd:.4f} "
        f"(estimated, not billed; pricing source: {c.source}). {c.note}",
        f"- Estimated cost of this run: ${c.run_total_usd:.4f}",
        f"- Requests: {r.sent} sent, {r.failed} failed, {r.retried} retried; "
        f"{r.infra_error_attempts} infrastructure-error records",
        "",
        "## Charts",
        "",
    ]
    out += [f"![{name}](../../charts/{metadata.run_id}/{name})" for name in chart_files] or [
        "No charts were generated for this run."
    ]
    out += ["", "## Limitations", ""]
    out += [f"- {item}" for item in LIMITATIONS]
    out += [
        f"- This run: {summary.n_attempts} attempts over "
        f"{len(summary.per_question)} questions; {summary.n_infra_errors} unresolved "
        "infrastructure errors; "
        f"{summary.overall.outcomes.get('invalid_answer', 0)} invalid and "
        f"{summary.overall.outcomes.get('cut_off', 0)} cut-off answers.",
        "",
        "Author interpretation: see the experiment README.",
        "",
    ]
    return "\n".join(out)


def write_processed(
    processed_dir: Path, summary: AnswerSummary, records: Sequence[AnswerRecord]
) -> dict[str, Path]:
    """Write ``answer_summary.json`` and ``answers_by_attempt.csv`` (latest record per attempt)."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    summary_path = processed_dir / "answer_summary.json"
    csv_path = processed_dir / "answers_by_attempt.csv"
    write_json(summary_path, summary)
    columns = [
        "attempt_id",
        "question_id",
        "repetition",
        "category",
        "outcome",
        "correct",
        "false_refusal",
        "correct_refusal",
        "made_up_answer",
        "context_hit",
        "citations_valid",
        "cites_relevant",
        "unsupported_identifiers",
        "invented_identifiers",
        "missing_key_facts",
        "embed_ms",
        "search_ms",
        "generation_ms",
        "total_ms",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "attempts",
        "error_kind",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for r in latest_by_attempt(records).values():
            writer.writerow(
                {
                    "attempt_id": r.attempt_id,
                    "question_id": r.question_id,
                    "repetition": r.repetition,
                    "category": r.category,
                    "outcome": r.outcome,
                    "correct": "" if r.correct is None else r.correct,
                    "false_refusal": "" if r.false_refusal is None else r.false_refusal,
                    "correct_refusal": "" if r.correct_refusal is None else r.correct_refusal,
                    "made_up_answer": "" if r.made_up_answer is None else r.made_up_answer,
                    "context_hit": r.context_hit,
                    "citations_valid": "" if r.citations_valid is None else r.citations_valid,
                    "cites_relevant": "" if r.cites_relevant is None else r.cites_relevant,
                    "unsupported_identifiers": " ".join(r.unsupported_identifiers),
                    "invented_identifiers": " ".join(r.invented_identifiers),
                    "missing_key_facts": " ".join(r.missing_key_facts),
                    "embed_ms": round(r.embed_ms, 3),
                    "search_ms": round(r.search_ms, 3),
                    "generation_ms": round(r.generation_ms, 3),
                    "total_ms": round(r.total_ms, 3),
                    "prompt_tokens": r.usage.prompt_tokens,
                    "completion_tokens": r.usage.completion_tokens,
                    "total_tokens": r.usage.total_tokens,
                    "attempts": r.attempts,
                    "error_kind": r.error_kind or "",
                }
            )
    return {"summary": summary_path, "csv": csv_path}
