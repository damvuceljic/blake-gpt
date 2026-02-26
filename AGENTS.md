# Agent Operating Instructions

Read [GUARDRAILS.md](GUARDRAILS.md) before any action.

## Default Workflow
1. Route intake files:
   - `python scripts/intake/route_intake.py --raw-dir data/intake/<period>/<pack_type>/raw --strict-core`
2. Extract/tokenize:
   - `python scripts/extract/tokenize_pack.py --manifest data/packs/<period>/<pack_type>/pack_manifest.json`
3. Run analyses:
   - `python scripts/analyze/hot_questions.py --pack-dir data/normalized/<period>/<pack_type>`
   - `python scripts/analyze/deck_proofing.py --pack-dir data/normalized/<period>/<pack_type>`
   - `python scripts/analyze/variance_watch.py --pack-dir data/normalized/<period>/<pack_type>`
4. Chat-first router:
   - `python scripts/chat/blake_mode.py --message "<request>"`

## Intake Boundaries
1. `data/intake/processed/**` is archive-only. Agents must never use it as raw input.
2. Raw processing inputs must stay under `data/intake/<period>/<pack_type>/raw/`.
3. After successful `process_month.py`, raw files are moved to `data/intake/processed/<period>/<pack_type>/<timestamp>/`.

## Skill Routing
Use these repo-local skills when intent matches:
1. `skills/th-repo-guardrails`
2. `skills/th-intake-router`
3. `skills/th-pack-tokenizer`
4. `skills/th-hot-questions`
5. `skills/th-deck-proofing`
6. `skills/th-variance-watch`
7. `skills/th-blake-mode`

## Output Style
1. Keep user-facing messages short and useful.
2. Prioritize material risks and actions.
3. Avoid long methodological explanations unless asked.
