"""Deterministic generator of the "large" corpus used by the experiment 02b stress tests."""

from rag_experiment.corpus_gen.build import (
    CHANGES_FILE,
    IDENTIFIERS_FILE,
    GeneratedCorpus,
    differences,
    generate,
    write_files,
)
from rag_experiment.corpus_gen.gates import GateError, GateReport, check_generated

__all__ = [
    "CHANGES_FILE",
    "IDENTIFIERS_FILE",
    "GateError",
    "GateReport",
    "GeneratedCorpus",
    "check_generated",
    "differences",
    "generate",
    "write_files",
]
