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

Assets are generated from data in `results/`, never from invented values. Original charts stay in `results/charts/`.

Assets live in a per-run subdirectory, `visual-assets/<run_id>/`. These images are generated locally for posting and are **not committed**: the repository ignores `experiments/*/linkedin/visual-assets/*/`. The README embeds the equivalent charts from `results/charts/<run_id>/` instead.

No assets exist yet. The generator is built when the first measured run needs it.
