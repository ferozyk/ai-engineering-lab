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


def _embedding_yaml(extra: str = "") -> str:
    return (
        "experiment_version: x\ncorpus_dir: c\nquestions_dev: d\nquestions_measured: m\n"
        "chunking: {max_chunk_chars: 10}\n"
        "embedding: {model_id: m/x, revision: null, device: cpu, batch_size: 4, "
        "max_seq_length: 64, normalize: true}\n"
        "index: {dir: .index, collection_prefix: p}\n"
        "retrieval: {top_k_eval: 10, top_k_generation: 5}\n"
        "generation: {prompt_version: a-1.0, temperature: 0.0, max_output_tokens: 100, "
        "llm_seed: null, request_timeout_seconds: 30}\n"
        "run: {repetitions: 3, order_seed: 1, rate_limit_per_minute: 15, "
        "daily_request_cap: 900, canary_question_ids: [Q01]}\n"
        "pricing: {reference_label: null, reference_prompt_usd_per_million: null, "
        "reference_completion_usd_per_million: null}\n" + extra
    )


def _write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "configs").mkdir(exist_ok=True)
    path = tmp_path / "configs" / "experiment.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_retrieval_config_is_loaded(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, _embedding_yaml()))
    assert config.embedding.model_id == "m/x" and config.embedding.revision is None
    assert config.index_dir == (tmp_path / ".index").resolve()
    assert config.results_dir == tmp_path.resolve() / "results"
    assert config.retrieval.top_k_generation == 5


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("device: cpu", "device: cuda"),
        ("batch_size: 4", "batch_size: 0"),
        ("top_k_generation: 5", "top_k_generation: 11"),
    ],
)
def test_invalid_retrieval_settings(tmp_path: Path, old: str, new: str) -> None:
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _embedding_yaml().replace(old, new)))


def test_generation_run_and_pricing_config(
    tmp_path: Path, experiment_config: ExperimentConfig
) -> None:
    config = load_config(_write(tmp_path, _embedding_yaml()))
    assert config.generation.prompt_version == "a-1.0" and config.generation.llm_seed is None
    assert config.run.canary_question_ids == ("Q01",) and config.run.daily_request_cap == 900
    assert config.pricing_reference.prompt_usd_per_million is None
    shipped = experiment_config
    assert shipped.generation.temperature == 0.0 and shipped.generation.max_output_tokens == 16384
    assert shipped.run.repetitions == 3 and shipped.run.rate_limit_per_minute == 15
    assert shipped.run.canary_question_ids == ("Q01", "Q05", "Q14")
    assert shipped.run.rate_limit_per_minute < 20 and shipped.run.daily_request_cap < 1000


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("temperature: 0.0", "temperature: 2.5"),
        ("temperature: 0.0", "temperature: -0.1"),
        ("max_output_tokens: 100", "max_output_tokens: 0"),
        ("request_timeout_seconds: 30", "request_timeout_seconds: 0"),
        ("repetitions: 3", "repetitions: 0"),
        ("rate_limit_per_minute: 15", "rate_limit_per_minute: -1"),
        ("daily_request_cap: 900", "daily_request_cap: 0"),
        ("canary_question_ids: [Q01]", "canary_question_ids: []"),
        ("reference_label: null", "reference_label: x, surprise: 1"),
        ("reference_prompt_usd_per_million: null", "reference_prompt_usd_per_million: -1"),
    ],
)
def test_invalid_generation_settings(tmp_path: Path, old: str, new: str) -> None:
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, _embedding_yaml().replace(old, new)))


def test_missing_generation_section_is_rejected(tmp_path: Path) -> None:
    text = "".join(
        line
        for line in _embedding_yaml().splitlines(keepends=True)
        if not line.startswith("generation:")
    )
    with pytest.raises(ConfigError, match="generation"):
        load_config(_write(tmp_path, text))
