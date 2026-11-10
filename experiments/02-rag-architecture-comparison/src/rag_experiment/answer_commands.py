"""The answer commands: ``preflight``, ``canary`` and ``run``, plus ``analyse``.

Real mode talks to OpenRouter; ``--fake`` uses a deterministic fake chat model, needs no key and
never touches the network. Simulated output goes only under ``results/dry-run/``.
"""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from ai_lab.benchmarking import (
    MinIntervalLimiter,
    PricingError,
    PricingSnapshot,
    RequestBudget,
    before_request_hook,
    package_versions,
    resolve_pricing,
    simulated_pricing,
)
from ai_lab.config import ConfigurationError, Settings
from ai_lab.llm import (
    ChatModel,
    FreeModelDailyRequests,
    LLMInfraError,
    OpenAIChatModel,
    OpenRouterClient,
    OpenRouterError,
)
from rag_experiment.config import ConfigError, ExperimentConfig
from rag_experiment.corpus import Corpus, load_manifest
from rag_experiment.embeddings.provider import SentenceTransformerProvider
from rag_experiment.evaluation import charts
from rag_experiment.evaluation.answer_analysis import AnswerSummary, summarise_answers
from rag_experiment.evaluation.answer_metrics import corpus_vocabulary
from rag_experiment.evaluation.answer_report import render_answer_report, write_processed
from rag_experiment.evaluation.answer_run import (
    AnswerRunMetadata,
    RunInputs,
    RunOutcome,
    RunPaths,
    completed_attempts,
    find_run,
    latest_by_attempt,
    load_records,
    make_answer_run_id,
    plan_attempts,
    run_attempts,
    write_json,
)
from rag_experiment.evaluation.dataset import Question, load_questions, validate_question_set
from rag_experiment.evaluation.facts import corpus_header_names
from rag_experiment.evaluation.retrieval_metrics import RetrievalSummary
from rag_experiment.evaluation.retrieval_run import build_metadata
from rag_experiment.generation.fake import FakeChatModel
from rag_experiment.generation.prompts import (
    PROMPT_VERSION,
    build_messages,
    check_prompt_version,
    prompt_hash,
)
from rag_experiment.generation.provider import Generator
from rag_experiment.ingestion.chunker import Chunk
from rag_experiment.retrieval.base import RetrievalResult, RetrievedChunk
from rag_experiment.retrieval.store import collection_name, open_local_store

EXTRA_PACKAGES = ("openai", "httpx", "matplotlib")
HTTP_TIMEOUT_SECONDS = 30.0
SMOKE_PROMPT = "Reply with the word OK."
SMOKE_MAX_TOKENS = 256
CHARS_PER_TOKEN = 4
CONTEXT_MARGIN = 1.3


class RunError(Exception):
    """A run cannot start or resume; the message is for the user."""


@dataclass
class PreparedRetrieval:
    """Retrieval done once per question, before any generation."""

    corpus: Corpus
    chunks: list[Chunk]
    retriever_name: str
    results: dict[str, RetrievalResult]
    model_id: str
    revision: str
    dimension: int
    collection: str
    deterministic: bool


@dataclass
class Setup:
    """Facts established before the first request."""

    model_id: str
    provider: str
    pricing: PricingSnapshot
    key_before: FreeModelDailyRequests | None


# ------------------------------------------------------------------------------ helpers


def question_path(config: ExperimentConfig, set_name: str) -> Path:
    """The question file of a set."""
    return config.questions_measured if set_name == "measured" else config.questions_dev


def select_questions(
    config: ExperimentConfig, set_name: str, ids: Sequence[str] | None
) -> list[Question]:
    """The questions of a set, optionally restricted to ``ids`` (kept in file order)."""
    questions = list(load_questions(question_path(config, set_name)))
    if ids is None:
        return questions
    known = {q.id for q in questions}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise RunError(f"unknown question ids in the {set_name} set: {unknown}")
    return [q for q in questions if q.id in set(ids)]


def find_retrieval_run(results_base: Path, set_name: str) -> str | None:
    """The newest committed (non-simulated) dense retrieval run of a question set."""
    raw = results_base / "raw"
    if not raw.is_dir():
        return None
    candidates = sorted(
        p.name
        for p in raw.iterdir()
        if f"-retrieval-{set_name}-" in p.name and (p / "retrieval.jsonl").is_file()
    )
    return candidates[-1] if candidates else None


def load_retrieval_summary(results_base: Path, run_id: str) -> tuple[RetrievalSummary, bool]:
    """The processed retrieval summary and whether the run was simulated."""
    for root in (results_base, results_base / "dry-run"):
        path = root / "processed" / run_id / "retrieval_summary.json"
        if path.is_file():
            summary = RetrievalSummary.model_validate_json(path.read_text(encoding="utf-8"))
            return summary, root != results_base
    raise RunError(f"no retrieval summary for run {run_id!r} under {results_base}")


def _initial_used(cap: int, key: FreeModelDailyRequests | None) -> int:
    if key is None:
        return 0
    return cap - min(cap, key.remaining)


def _one_line(text: str) -> str:
    return " ".join(text.split())


# ------------------------------------------------------------------------------ metadata


def build_run_metadata(
    *,
    config: ExperimentConfig,
    retrieval: PreparedRetrieval,
    paths: RunPaths,
    set_name: str,
    question_ids: Sequence[str],
    is_canary: bool,
    fake: bool,
    setup: Setup,
    started_at: datetime,
    planned: int,
    repetitions: int,
    outcome: RunOutcome | None,
    key_after: FreeModelDailyRequests | None,
    earlier: AnswerRunMetadata | None,
) -> AnswerRunMetadata:
    """Assemble the metadata from the files on disk (so it is right after any resume)."""
    base = build_metadata(
        config=config,
        corpus=retrieval.corpus,
        run_id=paths.run_id,
        set_name=set_name,
        question_path=question_path(config, set_name),
        retriever_name=retrieval.retriever_name,
        fake=fake,
        model_id=retrieval.model_id,
        revision=retrieval.revision,
        dimension=retrieval.dimension,
        collection=retrieval.collection,
        started_at=started_at,
        deterministic=retrieval.deterministic,
    )
    records = load_records(paths.answers)
    latest = latest_by_attempt(records)
    infra = [r for r in records if r.outcome == "infra_error"]
    ok = [r for r in records if r.outcome != "infra_error"]
    data = base.model_dump()
    data.update(
        kind="answers",
        package_versions={**base.package_versions, **package_versions(EXTRA_PACKAGES)},
    )
    gen = config.generation
    return AnswerRunMetadata(
        **data,
        provider=setup.provider,
        model_id=setup.model_id,
        models_served=sorted({r.model_served for r in records if r.model_served}),
        providers_served=sorted({r.provider for r in records if r.provider}),
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash(),
        generation=gen.model_dump(mode="json"),
        run={**config.run.model_dump(mode="json"), "repetitions": repetitions},
        pricing=setup.pricing,
        question_ids=list(question_ids),
        is_canary=is_canary,
        requests_sent=sum(r.attempts for r in records),
        failed_requests=sum(r.attempts for r in infra) + sum(max(0, r.attempts - 1) for r in ok),
        infra_errors=len(infra),
        attempts_planned=planned,
        attempts_completed=sum(1 for r in latest.values() if r.outcome != "infra_error"),
        free_model_daily_requests_before=setup.key_before,
        free_model_daily_requests_after=(
            key_after
            if key_after is not None
            else (earlier.free_model_daily_requests_after if earlier else None)
        ),
        halted=outcome.halted if outcome else False,
        halt_reason=outcome.halt_reason if outcome else None,
    )


# ------------------------------------------------------------------------------ outputs


def write_outputs(
    paths: RunPaths,
    metadata: AnswerRunMetadata,
    questions: Sequence[Question],
    results_base: Path,
    retrieval_run: str | None,
) -> tuple[AnswerSummary, list[str]]:
    """Summary, CSV, charts and report from the raw files. Makes no model request."""
    records = load_records(paths.answers)
    summary = summarise_answers(
        records, questions, question_set=metadata.question_set, pricing=metadata.pricing
    )
    write_processed(paths.processed, summary, records)
    notes: list[str] = []
    retrieval_summary: RetrievalSummary | None = None
    note = ""
    run_id = retrieval_run or find_retrieval_run(results_base, metadata.question_set)
    if run_id is None:
        notes.append("no retrieval run found: the Hit@K chart was skipped")
    else:
        retrieval_summary, retrieval_simulated = load_retrieval_summary(results_base, run_id)
        note = f"Retrieval data: run {run_id}" + (" (simulated)" if retrieval_simulated else "")
    ctx = charts.ChartContext(
        run_id=metadata.run_id,
        model_id=metadata.model_id,
        simulated=metadata.simulated,
        n_attempts=summary.n_scored,
    )
    drawn = charts.render_all(summary, retrieval_summary, ctx, paths.charts, note)
    report = render_answer_report(metadata, summary, charts.chart_names(drawn))
    paths.reports.mkdir(parents=True, exist_ok=True)
    (paths.reports / "answer_report.md").write_text(report, encoding="utf-8")
    return summary, notes


def summary_lines(summary: AnswerSummary, paths: RunPaths) -> list[str]:
    """A short console summary."""
    o = summary.overall
    lines = [
        f"run id: {summary.run_id}"
        + (" (SIMULATED, not a measurement)" if summary.simulated else ""),
        f"attempts: {summary.n_attempts} ({summary.n_scored} scored, "
        f"{summary.n_infra_errors} infrastructure errors)",
        f"outcomes: {o.outcomes}",
    ]
    ans, ref = o.answerable, o.correct_refusals
    if ans.value is not None:
        lines.append(
            f"correctness (answerable): {ans.numerator}/{ans.denominator} = {ans.value:.3f}"
        )
    if o.false_refusals.value is not None:
        fr = o.false_refusals
        lines.append(
            f"false refusal (answerable): {fr.numerator}/{fr.denominator} = {fr.value:.3f}"
        )
    if ref.value is not None:
        lines.append(
            f"correct refusal (unanswerable): {ref.numerator}/{ref.denominator} = {ref.value:.3f}"
        )
    lines += [f"{v.hypothesis}: {v.verdict} {v.evidence}".rstrip() for v in summary.verdicts]
    lines += [
        f"estimated cost per 1,000 questions: ${summary.cost.per_1000_questions_usd:.4f} "
        f"({summary.cost.source})",
        f"requests: {summary.requests.sent} sent, {summary.requests.failed} failed, "
        f"{summary.requests.retried} retried",
        f"report: {paths.reports / 'answer_report.md'}",
        f"charts: {paths.charts}",
    ]
    return lines


# ------------------------------------------------------------------------------ run


def _build_real_chat(
    settings: Settings, config: ExperimentConfig, model_id: str, budget: RequestBudget
) -> ChatModel:
    client = AsyncOpenAI(
        base_url=str(settings.openrouter_base_url),
        api_key=settings.require_openrouter_api_key(),
        timeout=config.generation.request_timeout_seconds,
        max_retries=0,
    )
    hook = before_request_hook(MinIntervalLimiter(config.run.rate_limit_per_minute), budget)
    return OpenAIChatModel(
        client=client,
        model=model_id,
        temperature=config.generation.temperature,
        max_tokens=config.generation.max_output_tokens,
        seed=config.generation.llm_seed,
        before_request=hook,
    )


async def _execute(
    *,
    config: ExperimentConfig,
    settings_loader: Callable[[], Settings],
    fake: bool,
    questions: Sequence[Question],
    all_questions: Sequence[Question],
    retrieval: PreparedRetrieval,
    paths: RunPaths,
    resume_meta: AnswerRunMetadata | None,
    repetitions: int,
    on_ready: Callable[[Setup], None],
    progress: Callable[[str], None],
) -> tuple[RunOutcome, FreeModelDailyRequests | None, Setup]:
    """Prepare the model, then run every attempt that is not yet complete."""
    cap = config.run.daily_request_cap
    records = load_records(paths.answers)
    skip = completed_attempts(records)
    plan = plan_attempts(questions, repetitions, config.run.order_seed)
    header_names = corpus_header_names(retrieval.corpus)
    inputs = RunInputs(
        paths=paths,
        run_id=paths.run_id,
        chunks=retrieval.chunks,
        header_names=header_names,
        corpus_vocab=corpus_vocabulary(retrieval.chunks, retrieval.corpus.specs),
        retrievals=retrieval.results,
        top_k=config.retrieval.top_k_generation,
        simulated=fake,
    )
    key_after: FreeModelDailyRequests | None = None
    if fake:
        setup = Setup("simulated-oracle", "simulated", simulated_pricing(), None)
        budget = RequestBudget(cap)
        chat_fake = FakeChatModel(
            all_questions, retrieval.chunks, before_request=_budget_hook(budget)
        )
        on_ready(setup)
        outcome = await run_attempts(
            inputs,
            Generator(chat_fake, simulated=True),
            plan,
            skip,
            budget,
            chat_fake.set_attempt,
            progress,
        )
        return outcome, None, setup

    settings = settings_loader()
    model_id = settings.require_llm_model()
    if resume_meta is not None and resume_meta.model_id != model_id:
        raise RunError(
            f"LLM_MODEL is {model_id!r} but the run was started with {resume_meta.model_id!r}; "
            "the model is never switched silently. Restore LLM_MODEL to resume."
        )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
        client = OpenRouterClient(
            base_url=str(settings.openrouter_base_url),
            api_key=settings.require_openrouter_api_key(),
            http=http,
        )
        key = await client.key_info()
        if resume_meta is not None:
            pricing = resume_meta.pricing
            key_before = (
                resume_meta.free_model_daily_requests_before or key.free_model_daily_requests
            )
        else:
            pricing = resolve_pricing(
                model_id, await client.list_models(), config.pricing_reference
            )
            key_before = key.free_model_daily_requests
        setup = Setup(model_id, settings.llm_provider, pricing, key_before)
        budget = RequestBudget(cap, _initial_used(cap, key.free_model_daily_requests))
        chat = _build_real_chat(settings, config, model_id, budget)
        on_ready(setup)
        try:
            outcome = await run_attempts(
                inputs, Generator(chat), plan, skip, budget, None, progress
            )
        finally:
            try:
                key_after = (await client.key_info()).free_model_daily_requests
            except OpenRouterError:
                key_after = None
    return outcome, key_after, setup


def _budget_hook(budget: RequestBudget) -> Callable[[], Awaitable[None]]:
    """A request hook that only counts against the budget (no throttling)."""

    async def hook() -> None:
        budget.consume()

    return hook


def execute_run(
    *,
    config: ExperimentConfig,
    settings_loader: Callable[[], Settings],
    results_base: Path,
    results_root: Path,
    retrieval: PreparedRetrieval,
    set_name: str,
    question_ids: Sequence[str] | None,
    is_canary: bool,
    fake: bool,
    resume: str | None,
    retrieval_run: str | None,
    all_questions: Sequence[Question],
) -> int:
    """Run (or resume) an answer run, then write the processed files, charts and report."""
    check_prompt_version(config.generation.prompt_version)
    started_at = datetime.now(UTC)
    earlier: AnswerRunMetadata | None = None
    if resume is not None:
        paths = find_run(results_base, resume)
        if (paths.root != results_base) != fake:
            raise RunError(
                f"run {resume!r} is {'simulated' if paths.root != results_base else 'real'}; "
                f"{'pass' if paths.root != results_base else 'omit'} --fake to resume it"
            )
        earlier = AnswerRunMetadata.model_validate_json(paths.metadata.read_text(encoding="utf-8"))
        if earlier.question_set != set_name:
            raise RunError(
                f"run {resume!r} used the {earlier.question_set!r} set, not {set_name!r}"
            )
        started_at = earlier.started_at
        is_canary, question_ids = earlier.is_canary, earlier.question_ids
    else:
        run_id = make_answer_run_id(set_name, retrieval.retriever_name, fake=fake, canary=is_canary)
        paths = RunPaths(results_root, run_id)
        if paths.raw.exists():
            raise RunError(f"run directory already exists: {paths.raw}")
    questions = select_questions(config, set_name, question_ids)
    repetitions = 1 if is_canary else config.run.repetitions
    planned = len(questions) * repetitions
    print(f"run id: {paths.run_id}")
    if fake:
        print("fake model: simulated run, files written under results/dry-run (not a measurement)")
    print(f"planned: {len(questions)} questions x {repetitions} repetitions = {planned}")

    outcome: RunOutcome
    key_after: FreeModelDailyRequests | None = None
    setup_holder: list[Setup] = []

    def ready(setup: Setup) -> None:
        setup_holder.append(setup)
        write_json(
            paths.metadata,
            build_run_metadata(
                config=config,
                retrieval=retrieval,
                paths=paths,
                set_name=set_name,
                question_ids=[q.id for q in questions],
                is_canary=is_canary,
                fake=fake,
                setup=setup,
                started_at=started_at,
                planned=planned,
                repetitions=repetitions,
                outcome=None,
                key_after=None,
                earlier=earlier,
            ),
        )

    try:
        outcome, key_after, _ = asyncio.run(
            _execute(
                config=config,
                settings_loader=settings_loader,
                fake=fake,
                questions=questions,
                all_questions=all_questions,
                retrieval=retrieval,
                paths=paths,
                resume_meta=earlier,
                repetitions=repetitions,
                on_ready=ready,
                progress=print,
            )
        )
    except KeyboardInterrupt:
        outcome = RunOutcome(halted=True, halt_reason="interrupted (Ctrl-C)")
    if not setup_holder:
        raise RunError("the run stopped before the first request")
    metadata = build_run_metadata(
        config=config,
        retrieval=retrieval,
        paths=paths,
        set_name=set_name,
        question_ids=[q.id for q in questions],
        is_canary=is_canary,
        fake=fake,
        setup=setup_holder[0],
        started_at=started_at,
        planned=planned,
        repetitions=repetitions,
        outcome=outcome,
        key_after=key_after,
        earlier=earlier,
    )
    write_json(paths.metadata, metadata)
    summary, notes = write_outputs(paths, metadata, questions, results_base, retrieval_run)
    print()
    print("\n".join(summary_lines(summary, paths)))
    for note in notes:
        print(f"note: {note}")
    if outcome.halted:
        print(f"HALTED: {outcome.halt_reason}")
        print(
            f"Resume with: rag-experiment run --set {set_name} --resume {paths.run_id}"
            + (" --fake" if fake else "")
        )
        return 1
    return 0


def analyse_run(
    config: ExperimentConfig, results_base: Path, run_id: str, retrieval_run: str | None
) -> int:
    """Rebuild the summary, report and charts of a run from its raw files (no requests)."""
    paths = find_run(results_base, run_id)
    metadata = AnswerRunMetadata.model_validate_json(paths.metadata.read_text(encoding="utf-8"))
    questions = select_questions(config, metadata.question_set, metadata.question_ids)
    summary, notes = write_outputs(paths, metadata, questions, results_base, retrieval_run)
    print("\n".join(summary_lines(summary, paths)))
    for note in notes:
        print(f"note: {note}")
    return 0


# ------------------------------------------------------------------------------ preflight


@dataclass(frozen=True)
class CheckResult:
    """One preflight check; ``detail`` is a single line."""

    name: str
    status: str  # "pass" | "warn" | "fail"
    detail: str


def index_status(config: ExperimentConfig, corpus: Corpus, chunks: Sequence[Chunk]) -> CheckResult:
    """Whether the local index of the configured collection is complete (no rebuild)."""
    provider = SentenceTransformerProvider(config.embedding)  # lazy: the model is not loaded
    collection = collection_name(
        config.index, corpus, config.chunking, provider.model_id, provider.revision
    )
    if not (config.index_dir / "qdrant").is_dir():
        return CheckResult("index", "fail", "no local index; run: rag-experiment index")
    with open_local_store(config.index_dir, collection) as store:
        count = store.count()
    if count != len(chunks):
        return CheckResult(
            "index",
            "fail",
            f"collection {collection} has {count} of {len(chunks)} chunks; "
            "run: rag-experiment index",
        )
    return CheckResult("index", "pass", f"collection {collection} is up to date ({count} chunks)")


def largest_prompt(
    config: ExperimentConfig, chunks: Sequence[Chunk], results_base: Path, run_id: str
) -> tuple[int, str]:
    """Largest prompt (characters) over the measured set, from a committed retrieval run."""
    by_id = {c.chunk_id: c for c in chunks}
    questions = {q.id: q for q in load_questions(config.questions_measured)}
    path = results_base / "raw" / run_id / "retrieval.jsonl"
    best, best_id = 0, ""
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        question = questions[record["question_id"]]
        top = record["ranked"][: config.retrieval.top_k_generation]
        context = [
            RetrievedChunk(
                chunk=by_id[r["chunk_id"]], score=r["score"], rank=r["rank"], retriever="dense"
            )
            for r in top
        ]
        size = sum(len(m["content"]) for m in build_messages(question.question, context))
        if size > best:
            best, best_id = size, question.id
    return best, best_id


def offline_checks(
    config: ExperimentConfig,
    settings: Settings,
    corpus: Corpus,
    chunks: Sequence[Chunk],
    results_base: Path,
    retrieval_run: str | None,
) -> list[CheckResult]:
    """Everything that needs no network and no model request."""
    results: list[CheckResult] = []
    try:
        check_prompt_version(config.generation.prompt_version)
        results.append(CheckResult("config", "pass", f"valid; prompt version {PROMPT_VERSION}"))
    except ValueError as exc:
        results.append(CheckResult("config", "fail", _one_line(str(exc))))
    if settings.llm_model is None:
        results.append(CheckResult("model", "fail", "LLM_MODEL is not set"))
    else:
        results.append(CheckResult("model", "pass", f"LLM_MODEL = {settings.llm_model}"))
    if settings.openrouter_api_key is None:
        results.append(CheckResult("api_key", "fail", "OPENROUTER_API_KEY is not set"))
    else:
        results.append(CheckResult("api_key", "pass", "OPENROUTER_API_KEY is set"))
    results.append(index_status(config, corpus, chunks))

    problems: list[str] = []
    header_names = corpus_header_names(corpus)
    for label, path in (("dev", config.questions_dev), ("measured", config.questions_measured)):
        problems += [
            f"[{label}] {p}"
            for p in validate_question_set(load_questions(path), corpus, chunks, header_names)
        ]
    manifest = load_manifest(config.manifest_path)
    digest = hashlib.sha256(config.questions_measured.read_bytes()).hexdigest()
    if manifest.eval_measured_status != "frozen":
        problems.append("the measured set is not frozen")
    elif manifest.eval_measured_checksum != digest:
        problems.append("the measured question file does not match the frozen checksum")
    if problems:
        results.append(CheckResult("questions", "fail", _one_line("; ".join(problems[:3]))))
    else:
        results.append(
            CheckResult("questions", "pass", f"valid; measured checksum {digest[:12]} is frozen")
        )

    run_id = retrieval_run or find_retrieval_run(results_base, "measured")
    if run_id is None:
        results.append(CheckResult("prompt_size", "warn", "no committed measured retrieval run"))
    else:
        size, qid = largest_prompt(config, chunks, results_base, run_id)
        results.append(
            CheckResult(
                "prompt_size",
                "pass",
                f"largest prompt {size:,} characters ({qid}, top "
                f"{config.retrieval.top_k_generation} context, from run {run_id})",
            )
        )

    canary = len(config.run.canary_question_ids)
    measured = len(load_questions(config.questions_measured)) * config.run.repetitions
    cap = config.run.daily_request_cap
    status = "pass" if canary + measured <= cap else "fail"
    results.append(
        CheckResult(
            "request_plan",
            status,
            f"canary {canary} + measured {measured} = {canary + measured} requests "
            f"(minimum, before retries) vs daily cap {cap}",
        )
    )
    return results


async def live_checks(
    config: ExperimentConfig,
    settings: Settings,
    http: httpx.AsyncClient,
    chat: ChatModel,
    largest_prompt_chars: int | None,
) -> list[CheckResult]:
    """The checks that touch the provider. ``chat`` is asked exactly one tiny question."""
    results: list[CheckResult] = []
    model_id = settings.require_llm_model()
    client = OpenRouterClient(
        base_url=str(settings.openrouter_base_url),
        api_key=settings.require_openrouter_api_key(),
        http=http,
    )
    models = None
    try:
        models = await client.list_models()
    except OpenRouterError as exc:
        results.append(CheckResult("model_listed", "fail", _one_line(str(exc))))
    if models is not None:
        info = next((m for m in models if m.id == model_id), None)
        if info is None:
            results.append(CheckResult("model_listed", "fail", f"{model_id!r} is not listed"))
        else:
            known = [
                v for v in (info.context_length, info.top_provider_context_length) if v is not None
            ]
            detail = (
                f"{model_id} listed; context length {min(known):,}"
                if known
                else (f"{model_id} listed; context length not reported")
            )
            results.append(CheckResult("model_listed", "pass", detail))
            if known and largest_prompt_chars is not None:
                needed = largest_prompt_chars / CHARS_PER_TOKEN * CONTEXT_MARGIN
                results.append(
                    CheckResult(
                        "context_window",
                        "pass" if min(known) >= needed else "fail",
                        f"largest prompt about {largest_prompt_chars / CHARS_PER_TOKEN:,.0f} "
                        f"tokens (characters / {CHARS_PER_TOKEN}, an estimate) x {CONTEXT_MARGIN} "
                        f"vs context {min(known):,}",
                    )
                )
        try:
            pricing = resolve_pricing(model_id, models, config.pricing_reference)
            results.append(CheckResult("pricing", "pass", f"{pricing.source}: {pricing.note}"))
        except PricingError as exc:
            results.append(CheckResult("pricing", "fail", _one_line(str(exc))))
    try:
        key = await client.key_info()
    except OpenRouterError as exc:
        results.append(CheckResult("key", "fail", _one_line(str(exc))))
    else:
        daily = key.free_model_daily_requests
        needed_requests = len(config.run.canary_question_ids) + 40 * config.run.repetitions
        if daily is None:
            results.append(CheckResult("key", "warn", "free-model counters not reported"))
        else:
            results.append(
                CheckResult(
                    "key",
                    "pass" if daily.remaining >= needed_requests else "warn",
                    f"{daily.remaining}/{daily.limit} free-model requests remaining today",
                )
            )
    try:
        reply = await chat.complete([{"role": "user", "content": SMOKE_PROMPT}])
    except LLMInfraError as exc:
        results.append(CheckResult("completion", "fail", _one_line(str(exc))))
    else:
        if reply.content and reply.usage.total_tokens > 0:
            results.append(
                CheckResult(
                    "completion",
                    "pass",
                    f"returned content and usage ({reply.usage.total_tokens} tokens, "
                    f"finish_reason {reply.finish_reason})",
                )
            )
        else:
            results.append(CheckResult("completion", "fail", "reply had no content or no usage"))
    return results


def format_report(results: Sequence[CheckResult]) -> str:
    """Render check results as a table."""
    width = max((len(r.name) for r in results), default=4)
    lines = [f"{'check'.ljust(width)}  status  detail", f"{'-' * width}  ------  ------"]
    lines += [f"{r.name.ljust(width)}  {r.status.upper():<6}  {r.detail}" for r in results]
    failed = sum(1 for r in results if r.status == "fail")
    warned = sum(1 for r in results if r.status == "warn")
    lines.append(f"\n{len(results)} checks: {failed} failed, {warned} warnings")
    return "\n".join(lines)


def preflight(
    config: ExperimentConfig,
    settings: Settings,
    corpus: Corpus,
    chunks: Sequence[Chunk],
    results_base: Path,
    retrieval_run: str | None,
    live: bool,
) -> int:
    """Run the preflight; returns the exit code (1 on any failure)."""
    try:
        results = offline_checks(config, settings, corpus, chunks, results_base, retrieval_run)
    except (ConfigError, ConfigurationError, ValueError, OSError) as exc:
        print(f"Error: {exc}")
        return 1
    if live:
        if any(r.status == "fail" and r.name in {"model", "api_key"} for r in results):
            results.append(CheckResult("live", "fail", "skipped: model or API key not set"))
        else:
            print("live checks will send 1 model request")
            run_id = retrieval_run or find_retrieval_run(results_base, "measured")
            size = largest_prompt(config, chunks, results_base, run_id)[0] if run_id else None
            budget = RequestBudget(config.run.daily_request_cap)
            chat = _build_real_chat_smoke(settings, config, budget)
            results += asyncio.run(_live(config, settings, chat, size))
    print(format_report(results))
    return 1 if any(r.status == "fail" for r in results) else 0


def _build_real_chat_smoke(
    settings: Settings, config: ExperimentConfig, budget: RequestBudget
) -> ChatModel:
    client = AsyncOpenAI(
        base_url=str(settings.openrouter_base_url),
        api_key=settings.require_openrouter_api_key(),
        timeout=config.generation.request_timeout_seconds,
        max_retries=0,
    )
    return OpenAIChatModel(
        client=client,
        model=settings.require_llm_model(),
        temperature=config.generation.temperature,
        max_tokens=SMOKE_MAX_TOKENS,
        seed=config.generation.llm_seed,
        max_attempts=1,
        before_request=_budget_hook(budget),
    )


async def _live(
    config: ExperimentConfig, settings: Settings, chat: ChatModel, size: int | None
) -> list[CheckResult]:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
        return await live_checks(config, settings, http, chat, size)
