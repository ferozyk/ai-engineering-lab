"""Derivation, wrapping and smoke renders of the sharing visuals (no results files needed)."""

import re
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from rag_experiment.evaluation.answer_run import AnswerRecord
from rag_experiment.visuals.data import (
    Numbers,
    RunInputs,
    Setup,
    VisualsDataError,
    build_numbers,
    check_same_setup,
    percent,
    round_half_up,
)
from rag_experiment.visuals.draw import HEIGHT, WIDTH, Canvas, resolve_font, wrap_words
from rag_experiment.visuals.infographic import build_infographic
from rag_experiment.visuals.render import write_pdf
from rag_experiment.visuals.slides import build_slides, slide_cover

RecordFactory = Callable[..., AnswerRecord]

# correct, false refusals, correct refusals, made up, total p50 ms, cost, calls, full coverage
FIGURES = {
    "A": (60, 10, 18, 0, 2000.0, 0.30, 1.0, 3),
    "B": (62, 8, 18, 0, 2400.0, 0.36, 1.0, 3),
    "C": (62, 9, 18, 0, 13000.0, 0.35, 1.0, 0),
    "D": (70, 1, 17, 1, 14000.0, 1.00, 3.25, 9),
}


def _summary(f: tuple[int, int, int, int, float, float, float, int]) -> dict[str, Any]:
    def frac(n: int, d: int) -> dict[str, int]:
        return {"numerator": n, "denominator": d}

    return {
        "n_scored": 120,
        "overall": {
            "answerable": frac(f[0], 102),
            "false_refusals": frac(f[1], 102),
            "correct_refusals": frac(f[2], 18),
        },
        "guardrails": {"made_up_answer": frac(f[3], 18)},
        "latency_ms": {"total": {"p50": f[4]}},
        "cost": {"per_1000_questions_usd": f[5]},
    }


def _runs(
    make_record: RecordFactory, model: str = "m", checksum: str = "c"
) -> dict[str, RunInputs]:
    runs: dict[str, RunInputs] = {}
    for x, f in FIGURES.items():
        records: list[AnswerRecord] = []
        for rep in (1, 2, 3):
            for qid in ("Q104", "Q128", "Q138"):
                records.append(
                    make_record(
                        attempt_id=f"{qid}-r{rep}",
                        question_id=qid,
                        repetition=rep,
                        correct=(x == "D"),
                        outcome="answered",
                        queries=("one", "two"),
                    )
                )
        runs[x] = RunInputs(
            run_id=f"run-{x}",
            summary=_summary(f),
            comparison={
                "correct": {"numerator": f[0], "denominator": 102},
                "model_calls_mean": f[6],
                "multi_endpoint_full_coverage": {"numerator": f[7], "denominator": 12},
            },
            metadata={
                "model_id": model,
                "question_set_checksum": checksum,
                "run": {"repetitions": 3},
            },
            records=records,
        )
    return runs


def _coverage(question_id: str, context_ids: Collection[str]) -> tuple[int, int]:
    return (2, 2) if question_id == "Q128" else (1, 1)


def _setup() -> Setup:
    return Setup(
        chunk_count=186,
        n_apis=5,
        n_answerable_questions=34,
        n_trick_questions=6,
        question_text={"Q104": "What `X`?", "Q128": "Which calls?"},
        coverage=_coverage,
    )


def test_rounding_is_half_up() -> None:
    assert round_half_up(2.5) == 3
    assert round_half_up(0.125, 2) == 0.13
    assert percent(77, 102) == 75
    assert percent(1, 8) == 13  # 12.5 rounds up
    with pytest.raises(VisualsDataError):
        percent(1, 0)


def test_derived_numbers(make_record: RecordFactory) -> None:
    numbers = build_numbers(_runs(make_record), _setup())
    get = numbers.entries
    assert get["deltaB"].value == 2
    assert get["deltaC"].value == 0
    assert get["deltaD"].value == 10
    assert get["slowC"].value == 7  # 13000 / 2000 = 6.5 rounds up
    assert get["timeRatio"].value == 7
    assert get["costRatio"].value == 3.3
    assert get["A.pct"].value == 59
    assert get["D.time_s"].value == 14.0
    assert get["q104.text"].value == "What X?"
    assert get["q104.D.right"].value == 3
    assert get["q104.A.right"].value == 0
    assert get["q128.D.covered"].value == 2
    assert get["q104.D.query2"].value == "two"


def test_registry_records_only_used_numbers(make_record: RecordFactory) -> None:
    numbers = build_numbers(_runs(make_record), _setup())
    numbers.slide = "slide-x"
    numbers.get("deltaB")
    used = numbers.used_entries()
    assert list(used) == ["deltaB"]
    assert used["deltaB"]["slides"] == ["slide-x"]
    with pytest.raises(VisualsDataError):
        numbers.get("nope")


def test_runs_must_share_model_and_question_set(make_record: RecordFactory) -> None:
    runs = _runs(make_record)
    assert check_same_setup(runs) == ("m", "c")
    other = RunInputs(
        run_id="run-D",
        summary=runs["D"].summary,
        comparison=runs["D"].comparison,
        metadata={"model_id": "other", "question_set_checksum": "c"},
        records=runs["D"].records,
    )
    with pytest.raises(VisualsDataError, match="different models"):
        check_same_setup({**runs, "D": other})
    changed = RunInputs(
        run_id="run-D",
        summary=runs["D"].summary,
        comparison=runs["D"].comparison,
        metadata={"model_id": "m", "question_set_checksum": "x"},
        records=runs["D"].records,
    )
    with pytest.raises(VisualsDataError, match="different question sets"):
        check_same_setup({**runs, "D": changed})


def test_missing_data_is_a_clear_error(make_record: RecordFactory) -> None:
    runs = _runs(make_record)
    broken = dict(runs["A"].summary)
    del broken["cost"]
    runs["A"] = RunInputs(
        "run-A", broken, runs["A"].comparison, runs["A"].metadata, runs["A"].records
    )
    with pytest.raises(VisualsDataError, match="cost"):
        build_numbers(runs, _setup())


def test_wrap_words_uses_measured_width() -> None:
    def measure(text: str) -> float:
        return 10.0 * len(text)

    assert wrap_words("aaa bbb ccc", 70, measure) == ["aaa bbb", "ccc"]
    assert wrap_words("averyverylongword x", 50, measure) == ["averyverylongword", "x"]
    assert wrap_words("go + search now", 120, measure) == ["go + search", "now"]


def test_smoke_render(make_record: RecordFactory, tmp_path: Path) -> None:
    numbers: Numbers = build_numbers(_runs(make_record), _setup())
    font = resolve_font()
    cover = slide_cover(numbers, font)
    info = build_infographic(numbers, font)
    for name, canvas in (("cover.png", cover), ("info.png", info)):
        path = tmp_path / name
        canvas.save_png(path)
        with Image.open(path) as image:
            assert image.size == (WIDTH, HEIGHT)
    assert isinstance(cover, Canvas)
    slides = build_slides(numbers, font)
    assert len(slides) == 9
    pdf = tmp_path / "c.pdf"
    write_pdf(slides, pdf)
    pages = re.findall(rb"/Type\s*/Page\b", pdf.read_bytes())
    assert len(pages) == 9
