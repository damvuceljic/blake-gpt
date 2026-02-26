---
name: th-pack-tokenizer
description: Extract monthly PPTX/XLSX pack files into token-efficient JSON/CSV artifacts with lineage metadata. Use after intake manifest creation, when preparing data for downstream analysis, or when chart/commentary evidence mapping is required.
---

# TH Pack Tokenizer

Primary UX note:
1. Blake should use `$th-blake-mode` for day-to-day ingestion. This tokenizer skill is advanced/engineering fallback.

1. Ensure a valid manifest exists:
   - `data/packs/<period>/<pack_type>/pack_manifest.json`
2. Run tokenizer:
   - `python scripts/extract/tokenize_pack.py --manifest data/packs/<period>/<pack_type>/pack_manifest.json`
3. Confirm outputs:
   - `data/normalized/<period>/<pack_type>/decks/`
   - `data/normalized/<period>/<pack_type>/workbooks/`
   - `data/normalized/<period>/<pack_type>/chunks/chunks.jsonl`

## Output Requirements
1. Workbook extract package must include:
   - `workbook_meta.json`
   - `external_links.json`
   - `lineage_flags.json`
   - `sheets/<sheet_slug>/values.csv`
   - `sheets/<sheet_slug>/formula_cells.csv`
   - `sheets/<sheet_slug>/named_ranges.json`
2. Deck extract package must include:
   - `deck_meta.json`
   - `slides/slide_<n>.json`
   - `charts/chart_<n>.json`
   - `slide_chart_map.json`
   - `boilerplate_filter_report.json`
3. Chunking must produce token-budgeted `chunks.jsonl`.

## Helper
Run:
- `python skills/th-pack-tokenizer/scripts/run_tokenizer.py --manifest data/packs/<period>/<pack_type>/pack_manifest.json`

See `references/token_guidelines.md` for chunking standards.
