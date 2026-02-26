---
name: th-intake-router
description: Route new monthly preview/close source files into validated pack manifests. Use when new PPTX/XLSX files arrive, when period/pack metadata must be inferred, or when intake needs deterministic classification before extraction.
---

# TH Intake Router

1. Confirm files are placed in `data/intake/<period>/<pack_type>/raw/`.
2. Never use archived inputs in `data/intake/processed/**`.
2. Run manifest routing:
   - `python scripts/intake/route_intake.py --raw-dir data/intake/<period>/<pack_type>/raw --strict-core`
3. Validate manifest:
   - `python scripts/intake/validate_manifest.py --manifest data/packs/<period>/<pack_type>/pack_manifest.json`
4. If period/pack inference is wrong, rerun with explicit flags:
   - `--period`
   - `--pack-type`
   - `--region`
   - `--source-mode`
5. If multiple offline workbook variants exist for the same pair:
   - provide `--pair-choice-file <json>`
6. If emergency run must proceed despite missing core files:
   - set `--allow-missing-core` explicitly

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
