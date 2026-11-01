# benchmarks

Benchmark design is documented in [methodology.md](methodology.md). It defines two scenarios (simple lookup and chained aggregation), three data volumes, 15 iterations per cell, interleaved execution, a first-run reliability protocol (offline dry run, preflight, canary, checkpointing) and the recorded run metadata. Runners are not yet implemented. Runs must also record the metadata listed in `docs/standards/benchmarking-standards.md`.
