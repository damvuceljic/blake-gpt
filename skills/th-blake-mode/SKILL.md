---
name: th-blake-mode
description: Chat-first workflow router for Blake. Use when user asks natural-language requests like ingesting monthly files, running hot questions, proofing decks, variance watch, or month-over-month comparison without technical CLI interaction.
---

# TH Blake Mode

1. Read `GUARDRAILS.md`.
2. Require Blake prompts to start with a `$` skill token.
3. Prefer `$th-blake-mode` as Blake's default daily entry point.
4. Use policy-aware hot-question defaults via `data/context/hot_questions_policy.default.json`.
5. Route user prompts to one of these intents:
   - ingest
   - hot questions
   - deck proofing
   - variance watch
   - compare prior month
6. Use one command:
   - `python scripts/chat/blake_mode.py --message "<user_prompt>"`
   - non-technical launcher: `python scripts/chat/blake_launcher.py`
7. Return concise executive output only.
8. Keep detailed command traces in `blake_mode_log.jsonl`.

## Routing Rules
1. Prompt contains ingest/intake/new files:
   - run end-to-end monthly processing (`process_month.py`).
2. Prompt contains hot questions/top risks/executive brief:
   - run `scripts/analyze/hot_questions.py` in challenge-card mode:
   - `--challenge-card-mode --strict-narrative --require-llm-attempt --use-llm-postprocess --policy-config data/context/hot_questions_policy.default.json`
3. Prompt contains proof/proofing/review deck:
   - run `scripts/analyze/deck_proofing.py`.
4. Prompt contains variance/bridge/reconcile:
   - run `scripts/analyze/variance_watch.py`.
5. Prompt contains compare/prior month:
   - run proofing with prior pack reference.

## Default Inputs
1. Use newest populated `data/intake/<period>/<pack_type>/raw` for ingestion if not specified.
2. Use newest normalized pack in `data/normalized/<period>/<pack_type>` if not specified.
3. Keep all raw files under `data/intake/.../raw`.
4. Never use `data/intake/processed/**` as intake input.
5. When confidence is low, preserve one clarifying question behavior.
6. For hot questions, enforce nuance checks:
   - at least one narrative evidence ref per non-watchout card
   - no bridge-only causal claims
   - explicit downgrade warning when LLM explainer is unavailable
   - preview semantic guard (`preview == LE`)
   - term guard + constructive LE framing
   - citation bundle completeness on returned cards

## Helper
Run:
- `python skills/th-blake-mode/scripts/run_blake_mode.py --message "<user_prompt>"`

See `references/intent_map.md` for explicit keyword-to-intent mapping.
