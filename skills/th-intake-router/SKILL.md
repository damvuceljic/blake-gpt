---
name: th-intake-router
description: Route new monthly preview/close source files into validated pack manifests. Use when new PPTX/XLSX files arrive, when period/pack metadata must be inferred, or when intake needs deterministic classification before extraction.
---

# TH Intake Router

1. Confirm files are placed in `data/intake/<period>/<pack_type>/raw/`.
2. Run manifest routing:
   - `python scripts/intake/route_intake.py --raw-dir data/intake/<period>/<pack_type>/raw`
3. Validate manifest:
   - `python scripts/intake/validate_manifest.py --manifest data/packs/<period>/<pack_type>/pack_manifest.json`
4. If period/pack inference is wrong, rerun with explicit flags:
   - `--period`
   - `--pack-type`
   - `--region`
   - `--source-mode`

## Classification Rules
1. Deck files:
   - `.pptx` with `preview` -> `preview_deck`
   - `.pptx` with `close` -> `close_deck`
2. Workbook files:
   - `.xlsx/.xlsm/.xls` with `preview` -> `preview_excel`
   - `.xlsx/.xlsm/.xls` with `close` -> `close_excel`
   - remaining workbook files -> `supporting_excel`
3. `source_mode`:
   - `both` default
   - override to `offline_values` or `lineage` only when known

## Helper
Run:
- `python skills/th-intake-router/scripts/run_intake.py --raw-dir data/intake/<period>/<pack_type>/raw`

See `references/manifest_contract.md` for required manifest fields.
