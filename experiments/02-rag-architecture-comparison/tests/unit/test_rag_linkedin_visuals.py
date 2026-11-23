"""Derivation, wrapping and smoke renders of the sharing visuals (no results files needed)."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from rag_experiment.evaluation.answer_run import AnswerRecord
from rag_experiment.visuals.cheatsheet import HINT, MEASURED, NOT_SHOWN, rows
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
from rag_experiment.visuals.iso import Iso, cuboid_faces
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


# question -> (category, right answers out of 3 for techniques A, B, C, D)
QUESTIONS = {
    "Q104": ("semantic", (0, 0, 0, 3)),
    "Q125": ("authentication", (0, 3, 3, 3)),
    "Q108": ("semantic", (3, 0, 2, 3)),
    "Q120": ("endpoint_discovery", (3, 3, 0, 3)),
    "Q128": ("multi_endpoint", (0, 3, 3, 3)),
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
        for qid, (category, counts) in QUESTIONS.items():
            for rep in (1, 2, 3):
                records.append(
                    make_record(
                        attempt_id=f"{qid}-r{rep}",
                        question_id=qid,
                        repetition=rep,
                        category=category,
                        correct=rep <= counts["ABCD".index(x)],
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


def _setup() -> Setup:
    return Setup(
        chunk_count=186,
        n_apis=5,
        n_answerable_questions=34,
        n_trick_questions=6,
        question_text={
            "Q104": "What `X`?",
            "Q125": "Which scopes?",
            "Q108": "How long?",
            "Q120": "Which endpoint?",
        },
        q120_pool_rank=1,
        q120_final_rank=7,
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
    assert get["q125.A.right"].value == 0
    assert get["q125.B.right"].value == 3
    assert get["q108.C.right"].value == 2
    assert get["q120.C.right"].value == 0
    assert get["q120.B.tries"].value == 3
    assert get["q120.pool_rank"].value == 1
    assert get["q120.final_rank"].value == 7
    assert get["gain.questions"].value == 2
    assert get["gain.semantic"].value == 2
    assert get["B.multi_correct"].value == 3
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
    assert len(build_slides(numbers, font)) == 11


def _all_canvases(make_record: RecordFactory) -> tuple[Numbers, dict[str, Canvas]]:
    numbers = build_numbers(_runs(make_record), _setup())
    font = resolve_font()
    canvases = {f"slide-{i}": c for i, c in enumerate(build_slides(numbers, font), start=1)}
    canvases["infographic"] = build_infographic(numbers, font)
    return numbers, canvases


def test_every_page_renders_at_full_size_and_pdf_has_11_pages(
    make_record: RecordFactory, tmp_path: Path
) -> None:
    _, canvases = _all_canvases(make_record)
    for name, canvas in canvases.items():
        path = tmp_path / f"{name}.png"
        canvas.save_png(path)
        with Image.open(path) as image:
            assert image.size == (1080, 1350), name
    pdf = tmp_path / "c.pdf"
    write_pdf([c for n, c in canvases.items() if n.startswith("slide-")], pdf)
    assert len(re.findall(rb"/Type\s*/Page\b", pdf.read_bytes())) == 11


def test_no_letter_labels_on_any_page(make_record: RecordFactory) -> None:
    _, canvases = _all_canvases(make_record)
    for name, canvas in canvases.items():
        for placed in canvas.placed:
            text = placed.text.strip()
            assert text not in {"A", "B", "C", "D"}, (name, text)
            assert not re.match(r"Pattern [A-D]\b", text), (name, text)


def test_isometric_projection_of_a_unit_cube() -> None:
    iso = Iso(0.0, 0.0, 1.0)
    top = cuboid_faces(iso, 0, 0, 0, 1, 1, 1)["top"]
    half = 3**0.5 / 2
    expected = [(0.0, -1.0), (half, -0.5), (0.0, 0.0), (-half, -0.5)]
    for got, want in zip(top, expected, strict=True):
        assert got == pytest.approx(want)


def test_tower_height_is_proportional_to_value() -> None:
    iso = Iso(100.0, 500.0, 2.0)

    def height(value: float) -> float:
        left = cuboid_faces(iso, 0, 0, 0, 10, 10, value)["left"]
        return left[0][1] - left[3][1]  # a vertical edge: bottom minus top

    assert height(77) / height(85) == pytest.approx(77 / 85)
    assert height(0.0) == pytest.approx(0.0)
    assert height(40) == pytest.approx(40 * 2.0)


def test_cheat_sheet_rows_label_the_evidence(make_record: RecordFactory) -> None:
    numbers = build_numbers(_runs(make_record), _setup())
    numbers.slide = "t"
    table = rows(numbers)
    assert table["A"].evidence == MEASURED
    assert table["D"].evidence == MEASURED
    assert table["B"].evidence == HINT
    assert table["C"].evidence == NOT_SHOWN
    assert f"≈{numbers.entries['slowC'].value}\u00d7" in table["C"].watch_out
    assert f"≈{numbers.entries['costRatio'].value}\u00d7" in table["D"].watch_out
    assert {"slowC", "costRatio", "timeRatio", "D.made_up"} <= set(numbers.used_entries())
