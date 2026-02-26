---
name: th-variance-watch
description: Validate variance bridges and driver narratives across normalized workbook extracts. Use when reviewing P&L variance quality, bridge integrity, period consistency, FX treatment, and completeness before executive submission.
---

# TH Variance Watch

1. Run variance checks:
   - `python scripts/analyze/variance_watch.py --pack-dir data/normalized/<period>/<pack_type>`
   - optional postprocess: `--use-llm-postprocess`
2. Focus output on:
   - mismatch risk
   - period consistency
   - FX treatment clarity
   - placeholder/incomplete content
3. Return structured issue log with severity and recommended fixes.

## Validation Priorities
1. Confirm bridge tabs contain formulas in extracted range.
2. Detect mixed period tokens (YTD/QTD/FY) in same analytical context.
3. Flag FX mentions without rate context.
4. Flag placeholders (`TBU`, `TBD`, `XXX`) and incomplete schedules.
5. Flag weak driver traceability where bridge decomposition is unclear.

## Helper
Run:
- `python skills/th-variance-watch/scripts/run_variance_watch.py --pack-dir data/normalized/<period>/<pack_type>`

See `references/issue_types.md` for issue classification definitions.
