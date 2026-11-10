"""Unit tests for configuration loading."""

from pathlib import Path

import pytest

from rag_experiment.config import ConfigError, ExperimentConfig, default_config_path, load_config

pytestmark = pytest.mark.unit


def test_shipped_config_resolves_paths(experiment_config: ExperimentConfig) -> None:
    assert experiment_config.experiment_version == "0.1.0"
    assert experiment_config.chunking.max_chunk_chars == 2400
    assert experiment_config.corpus_dir.is_dir()
    assert experiment_config.questions_dev.is_file()
    assert experiment_config.questions_measured.is_file()
    assert experiment_config.manifest_path.is_file()
    assert experiment_config.question_schema_path.is_file()
    assert default_config_path().is_file()


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Cannot read"):
        load_config(tmp_path / "nope.yaml")


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir()
    path = tmp_path / "configs" / "experiment.yaml"
    path.write_text(
        "experiment_version: x\ncorpus_dir: c\nquestions_dev: d\nquestions_measured: m\n"
        "chunking: {max_chunk_chars: 10}\nsurprise: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="invalid"):
        load_config(path)


def test_bad_chunk_size_and_shape(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir()
    path = tmp_path / "configs" / "experiment.yaml"
    path.write_text(
        "experiment_version: x\ncorpus_dir: c\nquestions_dev: d\nquestions_measured: m\n"
        "chunking: {max_chunk_chars: 0}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(path)
