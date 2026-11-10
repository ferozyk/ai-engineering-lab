"""Experiment configuration, loaded from ``configs/experiment.yaml``."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


class ChunkingConfig(BaseModel):
    """Chunker settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_chunk_chars: int = Field(gt=0)


class ExperimentConfig(BaseModel):
    """Paths and settings shared by every command. Paths are resolved against ``root``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_version: str
    corpus_dir: Path
    questions_dev: Path
    questions_measured: Path
    chunking: ChunkingConfig
    root: Path

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
    try:
        return ExperimentConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Config {path} is invalid: {exc}") from exc
