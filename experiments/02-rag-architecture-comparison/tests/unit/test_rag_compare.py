"""Unit tests for the cross-run comparison (hand-made summaries, no model)."""

import json
from pathlib import Path

import pytest

from rag_experiment.evaluation.compare import run_compare
from rag_experiment.evaluation.retrieval_metrics import QuestionRetrieval, summarize

pytestmark = pytest.mark.unit


def _rec(
    run: str, qid: str, category: str, rank: int | None, excluded: bool = False
) -> QuestionRetrieval:
    def hit(k: int) -> float:
        return float(rank is not None and rank <= k)

    hits = {1: hit(1), 3: hit(3), 5: hit(5), 10: hit(10)}
    return QuestionRetrieval(
        run_id=run,
        question_id=qid,
        category=category,
        paraphrase_of=None,
        retriever="x",
        k=10,
        excluded=excluded,
        ranked=(),
        relevant_chunk_ids=() if excluded else ("c",),
        n_relevant_sources=0 if excluded else 1,
        hit=hits,
        recall=dict(hits),
        precision=dict(hits),
        reciprocal_rank=0.0 if rank is None else 1 / rank,
        first_relevant_rank=rank,
        embed_ms=10.0,
        search_ms=2.0,
    )


def _write_run(base: Path, run_id: str, retriever: str, ranks: list[int | None]) -> None:
    categories = ["semantic", "exact_identifier", "unanswerable"]
    records = [
        _rec(run_id, f"Q{i}", categories[min(i, 2)], rank, excluded=i == 2)
        for i, rank in enumerate(ranks)
    ]
    summary = summarize(run_id, "measured", records, [])
    if retriever == "bm25":
        summary = summary.model_copy(update={"verdicts": ()})
    raw = base / "raw" / run_id
    raw.mkdir(parents=True)
    (raw / "run_metadata.json").write_text(json.dumps({"retriever": retriever}), "utf-8")
    (raw / "retrieval.jsonl").write_text(
        "".join(json.dumps(r.model_dump(mode="json")) + "\n" for r in records), "utf-8"
    )
    processed = base / "processed" / run_id
    processed.mkdir(parents=True)
    (processed / "retrieval_summary.json").write_text(summary.model_dump_json(), "utf-8")


def test_comparison_of_two_hand_made_runs(tmp_path: Path) -> None:
    _write_run(tmp_path, "run-dense", "dense", [1, 7, None])
    _write_run(tmp_path, "run-bm25", "bm25", [3, 1, None])
    paths = run_compare(tmp_path, ["run-dense", "run-bm25"], [], "demo")
    assert paths["json"] == tmp_path / "processed/comparisons/demo/comparison.json"
    assert paths["report"] == tmp_path / "reports/comparisons/demo/comparison.md"
    data = json.loads(paths["json"].read_text("utf-8"))
    dense = data["retrieval_runs"]["run-dense"]
    bm25 = data["retrieval_runs"]["run-bm25"]
    assert dense["hit"] == {"1": 0.5, "3": 0.5, "5": 0.5, "10": 1.0}
    assert bm25["hit"] == {"1": 0.5, "3": 1.0, "5": 1.0, "10": 1.0}
    assert dense["mrr"] == pytest.approx((1 + 1 / 7) / 2)
    assert dense["latency_total_p50_ms"] == pytest.approx(12.0)
    assert dense["hit_at_1_by_category"] == {"exact_identifier": 0.0, "semantic": 1.0}
    assert data["per_question"]["Q1"]["first_relevant_rank"] == {"run-dense": 7, "run-bm25": 1}
    text = paths["report"].read_text("utf-8")
    assert "| Hit@1 | 0.500 | 0.500 |" in text
    assert "| Hit@5 | 0.500 | 1.000 |" in text
    assert "| Q1 | exact_identifier | 7 | 1 |" in text
    assert "Q2" not in text.split("## Per question")[1].split("## Verdicts")[0]  # excluded
    assert "HA1" in text  # verdict table copied from the dense summary
    assert text.count("diagnostic run: no pre-registered hypotheses") == 1  # the bm25 run
    assert "no model was called" in text


def test_bad_name_and_missing_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid comparison name"):
        run_compare(tmp_path, ["x"], [], "../escape")
    with pytest.raises(ValueError, match="cannot read"):
        run_compare(tmp_path, ["nope"], [], "ok")


def test_comparison_shows_rerank_columns_only_when_present(tmp_path: Path) -> None:
    _write_run(tmp_path, "run-hybrid", "hybrid", [4, 7, None])
    run_id = "run-rerank"
    categories = ["semantic", "exact_identifier", "unanswerable"]
    records = [
        _rec(run_id, f"Q{i}", categories[min(i, 2)], rank, excluded=i == 2).model_copy(
            update={"retriever": "rerank", "rerank_ms": 40.0, "pool_first_relevant_rank": pool}
        )
        for i, (rank, pool) in enumerate([(1, 4), (None, None), (None, None)])
    ]
    summary = summarize(run_id, "measured", records, [])
    raw = tmp_path / "raw" / run_id
    raw.mkdir(parents=True)
    (raw / "run_metadata.json").write_text(json.dumps({"retriever": "rerank"}), "utf-8")
    (raw / "retrieval.jsonl").write_text(
        "".join(json.dumps(r.model_dump(mode="json")) + "\n" for r in records), "utf-8"
    )
    processed = tmp_path / "processed" / run_id
    processed.mkdir(parents=True)
    (processed / "retrieval_summary.json").write_text(summary.model_dump_json(), "utf-8")

    paths = run_compare(tmp_path, ["run-hybrid", run_id], [], "abc")
    text = paths["report"].read_text("utf-8")
    assert "| latency p50, retrieval total (ms) | 12.00 | 52.00 |" in text
    assert "| latency p50, rerank (ms) | - | 40.00 |" in text
    assert "| relevant chunk among candidates | - | 1/2 (0.500) |" in text
    assert "candidate rank: rerank" in text
    assert "| Q0 | semantic | 4 | 1 | 4 |" in text
    assert "| Q1 | exact_identifier | 7 | not in top 10 | not in candidates |" in text
    data = json.loads(paths["json"].read_text("utf-8"))
    assert data["retrieval_runs"][run_id]["pool_hit"]["numerator"] == 1
    assert data["retrieval_runs"]["run-hybrid"]["latency_rerank_p50_ms"] is None
