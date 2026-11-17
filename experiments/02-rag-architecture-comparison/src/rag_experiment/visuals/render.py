"""Load the committed results, render the visuals and write ``numbers.json``."""

import json
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from matplotlib import rc_context
from matplotlib.backends.backend_pdf import PdfPages

from rag_experiment.config import ExperimentConfig
from rag_experiment.corpus import load_corpus
from rag_experiment.evaluation.answer_run import load_records
from rag_experiment.evaluation.coverage import CoverageContext, attempt_coverage
from rag_experiment.evaluation.dataset import load_questions
from rag_experiment.ingestion.chunker import chunk_corpus
from rag_experiment.visuals.data import (
    COMPARISON_PATH,
    Numbers,
    RunInputs,
    Setup,
    VisualsDataError,
    build_numbers,
    check_same_setup,
    dig,
    read_json,
)
from rag_experiment.visuals.draw import BG, Canvas, LayoutError, resolve_font
from rag_experiment.visuals.infographic import build_infographic
from rag_experiment.visuals.slides import build_slides

ANSWER_RUNS = {
    "A": "20261110T221134Z-answers-measured-dense",
    "B": "20261116T224508Z-answers-measured-hybrid",
    "C": "20261117T090258Z-answers-measured-rerank",
    "D": "20261117T173854Z-answers-measured-agentic",
}
INGEST_RUN = "20261110T204546Z-retrieval-measured-dense"
OUTPUT_SUBDIR = Path("linkedin/visual-assets/linkedin-post-02")
CAROUSEL_PDF = "rag_patterns_carousel.pdf"
INFOGRAPHIC_PNG = "rag_patterns_infographic.png"


@dataclass(frozen=True)
class Outputs:
    """What a render wrote."""

    files: tuple[Path, ...]
    numbers_file: Path
    numbers_written: int


def default_out_dir(config: ExperimentConfig) -> Path:
    return config.root / OUTPUT_SUBDIR


def load_inputs(config: ExperimentConfig) -> tuple[dict[str, RunInputs], Setup]:
    """Read the four answer runs and the dataset facts from the committed files."""
    results = config.results_dir
    comparison = read_json(config.root / COMPARISON_PATH)
    runs: dict[str, RunInputs] = {}
    for x, run_id in ANSWER_RUNS.items():
        runs[x] = RunInputs(
            run_id=run_id,
            summary=read_json(results / "processed" / run_id / "answer_summary.json"),
            comparison=dig(comparison, f"answer_runs.{run_id}", COMPARISON_PATH),
            metadata=read_json(results / "raw" / run_id / "run_metadata.json"),
            records=load_records(results / "raw" / run_id / "answers.jsonl"),
        )
        if not runs[x].records:
            raise VisualsDataError(f"no answer records for {run_id}")
    questions = load_questions(config.questions_measured)
    chunks = chunk_corpus(load_corpus(config.corpus_dir), config.chunking)
    ingest = read_json(results / "raw" / INGEST_RUN / "ingest.json")
    ingest_chunks = int(dig(ingest, "index_build.chunks", f"{INGEST_RUN}/ingest.json"))
    if ingest_chunks != len(chunks):
        raise VisualsDataError(f"corpus has {len(chunks)} chunks, the indexed run {ingest_chunks}")
    ctx = CoverageContext(questions={q.id: q for q in questions}, chunks=chunks)

    def coverage(question_id: str, context_ids: Collection[str]) -> tuple[int, int]:
        return attempt_coverage(ctx, question_id, context_ids)

    return runs, Setup(
        chunk_count=ingest_chunks,
        n_apis=len(list(config.corpus_dir.glob("*.yaml"))),
        n_answerable_questions=sum(1 for q in questions if not q.constraints.must_abstain),
        n_trick_questions=sum(1 for q in questions if q.constraints.must_abstain),
        question_text={q.id: q.question for q in questions},
        coverage=coverage,
    )


def write_pdf(canvases: list[Canvas], path: Path) -> None:
    """One page per canvas."""
    with (
        rc_context({"pdf.fonttype": 42}),
        PdfPages(path, metadata={"Title": "RAG patterns"}) as pdf,
    ):
        for canvas in canvases:
            pdf.savefig(canvas.fig, facecolor=BG)


def _check(canvases: dict[str, Canvas]) -> None:
    problems = [f"{name}: {p}" for name, c in canvases.items() for p in c.check()]
    if problems:
        raise LayoutError("\n".join(problems))


def render(config: ExperimentConfig, out_dir: Path, what: str) -> Outputs:
    """Render ``carousel``, ``infographic`` or ``all`` into ``out_dir``."""
    runs, setup = load_inputs(config)
    model, checksum = check_same_setup(runs)
    numbers = build_numbers(runs, setup)
    font = resolve_font()
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    canvases: dict[str, Canvas] = {}
    if what in ("carousel", "all"):
        for i, canvas in enumerate(build_slides(numbers, font), start=1):
            canvases[f"slide-{i:02d}"] = canvas
    if what in ("infographic", "all"):
        canvases["infographic"] = build_infographic(numbers, font)
    for name, canvas in canvases.items():
        path = out_dir / (INFOGRAPHIC_PNG if name == "infographic" else f"{name}.png")
        canvas.save_png(path)
        files.append(path)
    slides = [c for n, c in canvases.items() if n.startswith("slide-")]
    if slides:
        pdf_path = out_dir / CAROUSEL_PDF
        with (
            rc_context({"pdf.fonttype": 42}),
            PdfPages(pdf_path, metadata={"Title": "RAG patterns"}) as pdf,
        ):
            for canvas in slides:
                pdf.savefig(canvas.fig, facecolor=BG)
        files.append(pdf_path)
    _check(canvases)  # after saving, so a flagged page can still be inspected
    numbers_file = out_dir / "numbers.json"
    written = _write_numbers(numbers_file, numbers, font, model, checksum, runs, what != "all")
    return Outputs(tuple(files), numbers_file, written)


def _write_numbers(
    path: Path,
    numbers: Numbers,
    font: str,
    model: str,
    checksum: str,
    runs: dict[str, RunInputs],
    merge: bool,
) -> int:
    used = numbers.used_entries()
    if merge and path.is_file():  # a partial render keeps the other part's entries
        previous: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")).get("numbers", {})
        used = {**previous, **used}
    payload = {
        "font": font,
        "canvas": "1080x1350 px (5.4 x 6.75 in at 200 dpi)",
        "colours": "Okabe-Ito set (A #0072B2, B #E69F00, C #CC79A7, D #009E73); validator not run",
        "model_id": model,
        "question_set_checksum": checksum,
        "answer_runs": {x: r.run_id for x, r in runs.items()},
        "numbers": used,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(used)
