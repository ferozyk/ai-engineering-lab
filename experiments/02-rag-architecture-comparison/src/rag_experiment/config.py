"""Experiment configuration, loaded from ``configs/experiment.yaml``."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_lab.benchmarking import PricingReference


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


class ChunkingConfig(BaseModel):
    """Chunker settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_chunk_chars: int = Field(gt=0)


class EmbeddingConfig(BaseModel):
    """Embedding model settings. The model id lives in the config file, never in code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1)
    revision: str | None = None
    device: Literal["cpu", "mps"]
    batch_size: int = Field(gt=0)
    # Caps memory use. Chunks are at most a few hundred tokens, so no chunk is truncated;
    # the ``index`` command warns if one ever exceeds this.
    max_seq_length: int = Field(gt=0)
    normalize: bool
    # None lets the loader choose the weights file. False forces the legacy PyTorch file in the
    # pinned snapshot: without it, transformers 5 also loads an automatic safetensors conversion
    # published under a separate, unpinned Hub revision. See docs/architecture.md section 6.
    use_safetensors: bool | None = None


class IndexConfig(BaseModel):
    """Where the local vector index and embedding cache live (relative to the experiment)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dir: Path
    collection_prefix: str = Field(min_length=1)


class RetrievalConfig(BaseModel):
    """Retrieval depth settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_k_eval: int = Field(gt=0)
    top_k_generation: int = Field(gt=0)

    @model_validator(mode="after")
    def _generation_within_eval(self) -> "RetrievalConfig":
        if self.top_k_generation > self.top_k_eval:
            raise ValueError("top_k_generation must be <= top_k_eval")
        return self


class HybridConfig(BaseModel):
    """BM25 and rank-fusion settings for the hybrid retriever."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bm25_k1: float = Field(gt=0)
    bm25_b: float = Field(ge=0.0, le=1.0)
    rrf_k: int = Field(gt=0)
    candidate_depth: int = Field(gt=0)  # top-N taken from each list before fusion


class RerankConfig(BaseModel):
    """Cross-encoder reranker settings. The model id and a pinned revision live here only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)  # required: an unpinned reranker is not reproducible
    device: Literal["cpu", "mps"]
    batch_size: int = Field(gt=0)
    max_length: int = Field(gt=0)  # tokens per question + chunk pair
    candidate_depth: int = Field(gt=0)  # top-N of the hybrid ranking that is re-ordered
    use_safetensors: bool | None = None


class GenerationConfig(BaseModel):
    """Generation settings. The model id is not here: it comes from ``LLM_MODEL``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int = Field(gt=0)
    llm_seed: int | None = None
    request_timeout_seconds: int = Field(gt=0)


class AgentConfig(BaseModel):
    """Settings of the agentic pipeline (architecture D)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = Field(min_length=1)
    max_searches: int = Field(gt=0)  # searches per question, over the whole loop
    results_per_search: int = Field(gt=0)  # top-N of the search tool returned per query
    max_context_chunks: int = Field(gt=0)  # distinct chunks handed to the judge and the answer
    max_planned_queries: int = Field(gt=0)  # queries the planner may propose up front

    @model_validator(mode="after")
    def _planned_within_searches(self) -> "AgentConfig":
        if self.max_planned_queries > self.max_searches:
            raise ValueError("agent.max_planned_queries must be <= agent.max_searches")
        return self


class RunConfig(BaseModel):
    """How an answer run is scheduled and throttled."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repetitions: int = Field(gt=0)
    order_seed: int
    rate_limit_per_minute: int = Field(gt=0)
    daily_request_cap: int = Field(gt=0)
    canary_question_ids: tuple[str, ...] = Field(min_length=1)


class PricingConfig(BaseModel):
    """Fallback price, used only when no list price can be found for the model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_label: str | None = None
    reference_prompt_usd_per_million: float | None = Field(default=None, ge=0.0)
    reference_completion_usd_per_million: float | None = Field(default=None, ge=0.0)


class QuestionSetConfig(BaseModel):
    """A question file and the name of the corpus its questions were written against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: Path
    corpus: str = Field(min_length=1)


QUESTION_SET_NAMES = ("dev", "measured", "stress")


class ExperimentConfig(BaseModel):
    """Paths and settings shared by every command. Paths are resolved against ``root``.

    ``corpus_dir``, ``questions_dev`` and ``questions_measured`` are the original keys and keep
    working: they are the ``clean`` corpus and the ``dev`` and ``measured`` question sets. When
    ``corpora`` and ``question_sets`` are not written in the file they are filled in from them.
    ``corpus_dir`` is also the corpus the commands work on; :meth:`for_set` and
    :meth:`for_corpus` return a copy that points it at another named corpus.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_version: str
    corpus_dir: Path
    questions_dev: Path
    questions_measured: Path
    corpora: dict[str, Path] = Field(default_factory=dict)
    question_sets: dict[str, QuestionSetConfig] = Field(default_factory=dict)
    corpus_name: str = "clean"  # which entry of ``corpora`` ``corpus_dir`` currently is
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    index: IndexConfig
    retrieval: RetrievalConfig
    hybrid: HybridConfig
    rerank: RerankConfig
    generation: GenerationConfig
    agent: AgentConfig
    run: RunConfig
    pricing: PricingConfig
    root: Path

    @model_validator(mode="before")
    @classmethod
    def _default_named_entries(cls, data: object) -> object:
        """Fill ``corpora`` and ``question_sets`` from the original keys when they are absent."""
        if not isinstance(data, dict):
            return data
        filled = dict(data)
        if not filled.get("corpora"):
            filled["corpora"] = {"clean": filled.get("corpus_dir")}
        if not filled.get("question_sets"):
            filled["question_sets"] = {
                "dev": {"path": filled.get("questions_dev"), "corpus": "clean"},
                "measured": {"path": filled.get("questions_measured"), "corpus": "clean"},
            }
        return filled

    @model_validator(mode="after")
    def _named_entries_are_consistent(self) -> "ExperimentConfig":
        if self.corpora.get("clean") != self.corpus_dir:
            raise ValueError("corpora.clean must be the same folder as corpus_dir")
        for name, original in (("dev", self.questions_dev), ("measured", self.questions_measured)):
            entry = self.question_sets.get(name)
            if entry is None or entry.path != original or entry.corpus != "clean":
                raise ValueError(f"question_sets.{name} must match the original key and use clean")
        for name, entry in self.question_sets.items():
            if name not in QUESTION_SET_NAMES:
                raise ValueError(f"unknown question set {name!r}; expected {QUESTION_SET_NAMES}")
            if entry.corpus not in self.corpora:
                raise ValueError(f"question_sets.{name} uses an unknown corpus {entry.corpus!r}")
        return self

    @model_validator(mode="after")
    def _depth_covers_evaluation(self) -> "ExperimentConfig":
        if self.hybrid.candidate_depth < self.retrieval.top_k_eval:
            raise ValueError("hybrid.candidate_depth must be >= retrieval.top_k_eval")
        if self.rerank.candidate_depth < self.retrieval.top_k_eval:
            raise ValueError("rerank.candidate_depth must be >= retrieval.top_k_eval")
        return self

    @property
    def pricing_reference(self) -> PricingReference:
        """The configured fallback price in the shared pricing type."""
        return PricingReference(
            label=self.pricing.reference_label,
            prompt_usd_per_million=self.pricing.reference_prompt_usd_per_million,
            completion_usd_per_million=self.pricing.reference_completion_usd_per_million,
        )

    def question_set_path(self, name: str) -> Path:
        """The question file of a set; raises ``ValueError`` for a set that is not configured."""
        entry = self.question_sets.get(name)
        if entry is None:
            raise ValueError(
                f"unknown question set {name!r}; configured: {sorted(self.question_sets)}"
            )
        return entry.path

    def require_question_set(self, name: str) -> Path:
        """The question file of a set that must already exist (the stress set is written later)."""
        path = self.question_set_path(name)
        if not path.is_file():
            raise ConfigError(f"{name} question set not written yet ({path} does not exist)")
        return path

    def question_set_corpus(self, name: str) -> str:
        """The name of the corpus a question set is bound to."""
        entry = self.question_sets.get(name)
        if entry is None:
            raise ValueError(
                f"unknown question set {name!r}; configured: {sorted(self.question_sets)}"
            )
        return entry.corpus

    def for_corpus(self, name: str) -> "ExperimentConfig":
        """A copy whose ``corpus_dir`` is the named corpus (the same folder when unchanged)."""
        path = self.corpora.get(name)
        if path is None:
            raise ValueError(f"unknown corpus {name!r}; configured: {sorted(self.corpora)}")
        return self.model_copy(update={"corpus_dir": path, "corpus_name": name})

    def for_set(self, name: str) -> "ExperimentConfig":
        """A copy bound to the corpus of a question set."""
        return self.for_corpus(self.question_set_corpus(name))

    @property
    def index_dir(self) -> Path:
        """The local index folder (gitignored)."""
        return self.index.dir

    @property
    def results_dir(self) -> Path:
        """The results folder of this experiment."""
        return self.root / "results"

    @property
    def manifest_path(self) -> Path:
        """The dataset manifest, next to the corpus folder."""
        return self.corpus_dir.parent / "manifest.json"

    @property
    def question_schema_path(self) -> Path:
        """The JSON Schema for question records."""
        return self.questions_dev.parent / "question.schema.json"


def default_config_path() -> Path:
    """The shipped config file, located relative to the package so any working directory works."""
    return Path(__file__).resolve().parents[2] / "configs" / "experiment.yaml"


def load_config(path: Path) -> ExperimentConfig:
    """Load the config. Relative paths are resolved against the experiment folder."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Cannot read config {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config {path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Config {path} must be a mapping")
    root = path.resolve().parent.parent
    for key in ("corpus_dir", "questions_dev", "questions_measured"):
        value = raw.get(key)
        if isinstance(value, str):
            raw[key] = str((root / value).resolve())
    corpora = raw.get("corpora")
    if isinstance(corpora, dict):
        raw["corpora"] = {
            k: str((root / v).resolve()) if isinstance(v, str) else v for k, v in corpora.items()
        }
    question_sets = raw.get("question_sets")
    if isinstance(question_sets, dict):
        for entry in question_sets.values():
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                entry["path"] = str((root / entry["path"]).resolve())
    raw["root"] = str(root)
    index = raw.get("index")
    if isinstance(index, dict) and isinstance(index.get("dir"), str):
        index["dir"] = str((root / index["dir"]).resolve())
    try:
        return ExperimentConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Config {path} is invalid: {exc}") from exc
