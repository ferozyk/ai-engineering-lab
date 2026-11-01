# visual-assets

LinkedIn-ready graphics.

- Landscape: 1200 x 627 px
- Portrait: 1080 x 1350 px

Each asset should include:

- [ ] Experiment title
- [ ] Compared approaches
- [ ] Measured findings
- [ ] One takeaway
- [ ] Repository link

Assets live in a per-run subdirectory, `visual-assets/<run_id>/`, and are produced by `uv run mcp-vs-code-mode linkedin-assets <run_id>` (or `publish <run_id>`):

- `linkedin-landscape.png` (1200 x 627): tokens and p50 latency against volume, plus one generated takeaway sentence.
- `linkedin-portrait.png` (1080 x 1350): headline reduction figure, compact results table, tokens chart and footer.

Dry-run images are written under the gitignored `results/dry-run/<run_id>/linkedin/` and are watermarked as simulated.

Assets are generated from data in `results/`, never from invented values. Original charts stay in `results/charts/`.

These images are generated locally for posting and are **not committed** (`visual-assets/*/` is gitignored). The README embeds the equivalent charts from `results/charts/<run_id>/` instead.
