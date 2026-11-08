# datasets

Everything here is synthetic. No real bank, customer, credential or specification is used. "Lab Bank" is a fictional organisation.

| Item | Location | Status |
|---|---|---|
| Corpus: five Lab Bank OpenAPI 3.1 YAML files | `corpus/` | Pending. Written in Stage 2. |
| Evaluation set: questions with labelled ground truth | `evaluation/` | Draft. Schema and three illustrative records exist; the full set is written in Stage 2. |

The design of both is in [docs/dataset-design.md](../docs/dataset-design.md) and [docs/evaluation-methodology.md](../docs/evaluation-methodology.md).

## Versioning

- **Corpus version:** semantic version, plus a SHA-256 checksum computed over the sorted corpus files.
- **Evaluation set version:** its own version number.
- Both are recorded in the metadata of every run, so a result can always be tied to the exact data that produced it.
- The evaluation set is frozen and versioned before any measured run.
