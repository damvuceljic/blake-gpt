---
name: th-intake-router
description: Route new monthly preview/close source files into validated pack manifests. Use when new PPTX/XLSX files arrive, when period/pack metadata must be inferred, or when intake needs deterministic classification before extraction.
---

# TH Intake Router

1. Confirm files are placed in `data/intake/<period>/<pack_type>/raw/`.
2. Never use archived inputs in `data/intake/processed/**`.
3. Default behavior is full ingest (recommended):
   - `python skills/th-intake-router/scripts/run_intake.py --raw-dir data/intake/<period>/<pack_type>/raw --period <period> --pack-type <pack_type> --strict-core`
4. Advanced engineering-only modes:
   - route only: `--route-only`
   - tokenize only: `--tokenize-only --manifest <path>`
   - note: tokenize-only expects manifest source files to still exist in `raw/` (pre-archive)
5. If period/pack inference is wrong, rerun with explicit flags:
   - `--period`
   - `--pack-type`
   - `--region`
   - `--source-mode`
6. If multiple offline workbook variants exist for the same pair:
   - provide `--pair-choice-file <json>`
7. If emergency run must proceed despite missing core files:
   - set `--allow-missing-core` explicitly
8. Unsupported files (for example `.pdf`) in raw folder fail intake with an actionable error.

## Classification Rules
1. Deck files:
   - `.pptx` with `preview` -> `preview_deck`
   - `.pptx` with `close` -> `close_deck`
2. Workbook files:
   - core template workbook + preview + formulas -> `preview_formula_workbook`
   - core template workbook + preview + offline -> `preview_offline_workbook`
   - core template workbook + close + formulas -> `close_formula_workbook`
   - core template workbook + close + offline -> `close_offline_workbook`
   - remaining workbook files -> `supporting_excel`
3. `source_mode`:
   - `both` default
   - override to `offline_values` or `lineage` only when known

## Helper
Run:
- `python skills/th-intake-router/scripts/run_intake.py --raw-dir data/intake/<period>/<pack_type>/raw`

See `references/manifest_contract.md` for required manifest fields.
