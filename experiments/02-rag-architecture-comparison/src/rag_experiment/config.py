"""Experiment configuration, loaded from ``configs/experiment.yaml``."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


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


class ExperimentConfig(BaseModel):
    """Paths and settings shared by every command. Paths are resolved against ``root``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_version: str
    corpus_dir: Path
    questions_dev: Path
    questions_measured: Path
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    index: IndexConfig
    retrieval: RetrievalConfig
    root: Path

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
    raw["root"] = str(root)
    index = raw.get("index")
    if isinstance(index, dict) and isinstance(index.get("dir"), str):
        index["dir"] = str((root / index["dir"]).resolve())
    try:
        return ExperimentConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Config {path} is invalid: {exc}") from exc
