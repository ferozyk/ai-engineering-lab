"""Generate (or, with ``--check``, verify) the large corpus in ``datasets/corpus-large/``.

This is the same code as ``uv run rag-experiment generate-corpus``; the script exists so the
corpus can be rebuilt without remembering the command::

    uv run python scripts/generate_large_corpus.py [--check]
"""

import sys

from rag_experiment.cli import main

if __name__ == "__main__":
    sys.exit(main(["generate-corpus", *sys.argv[1:]]))
