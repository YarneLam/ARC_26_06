# Changelog

## 2026-11-16

- Grouped each analysis's source and results in its own top-level folder:
  `window_count/src/main.py` and `window_count/results/run-.../result.json`.
  The shared `runall.py` and `settings.py` are now at the template root.
  Register additional analysis folder names in `ANALYSES`.
- The optional `--results-dir` override retains its separate output-root layout.
  Existing results are left untouched.
  The shared runner opens the IFC once for the registered analyses.

- Initial starter: count IFC windows using an import-safe callable function.
- Added a local runner that writes JSON to a new folder on each run.
- Added `settings.py` for the local model path, keeping setup separate from
  the analysis. A command-line path can still override it.
- No automatic publishing, run metadata or engineering assessment.

Add dated entries for your meaningful changes and explain their effect on the
receiving team. Routine executions do not need changelog entries.
