---
name: th-deck-proofing
description: Audit normalized finance decks for commentary-number mismatch, stale text risk, missing slide hygiene, and disclosure consistency issues. Use before executive deck circulation or when proofing concerns are raised.
---

# TH Deck Proofing

1. Run proofing on normalized pack:
   - `python scripts/analyze/deck_proofing.py --pack-dir data/normalized/<period>/<pack_type>`
   - optional postprocess: `--use-llm-postprocess`
2. For stale commentary checks, include prior pack:
   - `python scripts/analyze/deck_proofing.py --pack-dir data/normalized/<period>/<pack_type> --prior-pack-dir data/normalized/<prior_period>/<pack_type>`
3. Deliver issue log with:
   - location
   - issue type
   - severity
   - recommended fix
   - evidence refs

## Scope of Checks
1. Commentary vs numeric/format sign mismatches.
2. Missing note text and missing usable titles.
3. Outdated repeated narrative from prior period.
4. Consistency markers (GAAP/IFRS labeling support).
5. Slide hygiene and confidentiality/disclaimer presence.

## Helper
Run:
- `python skills/th-deck-proofing/scripts/run_proofing.py --pack-dir data/normalized/<period>/<pack_type>`

See `references/issue_types.md` for issue taxonomy.
