# datasets

Everything here is synthetic. No real bank, customer, credential or specification is used. "Lab Bank" is a fictional organisation.

| Item | Location | Status |
|---|---|---|
| Corpus: five Lab Bank OpenAPI 3.1 YAML files | `corpus/` | Version 1.0.0. |
| Development questions (Q01 to Q15) | `evaluation/questions-dev.jsonl` | Used to build and debug the pipeline. |
| Measured questions (Q101 to Q140) | `evaluation/questions-measured.jsonl` | Frozen at version 1.0.0 (2026-11-11) after maintainer review; checksum in `manifest.json`. |
| Versions and corpus checksum | `manifest.json` | Checked by a test and by `validate-dataset`. |

The design of both is in [docs/dataset-design.md](../docs/dataset-design.md) and [docs/evaluation-methodology.md](../docs/evaluation-methodology.md).

## Versioning

- **Corpus version:** semantic version, plus a SHA-256 checksum computed over the sorted corpus files.
- **Evaluation set version:** its own version number.
- Both are recorded in the metadata of every run, so a result can always be tied to the exact data that produced it.
- The evaluation set is frozen and versioned before any measured run.

## Manifest and checksum

`manifest.json` records the corpus version, the corpus SHA-256 checksum, the version of each question set and the status of the measured set. The checksum is computed over `name + newline + file bytes` for every corpus file in name order. Any edit to a corpus file changes it, and a test fails until the manifest is updated on purpose.

Run `uv run rag-experiment validate-dataset` to check the corpus, the chunks and both question files.
