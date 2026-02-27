---
name: th-hot-questions
description: Generate concise CFO-level executive briefs from normalized monthly pack artifacts. Use when Blake asks hot questions after ingesting latest preview/close files, or when rapid risk/opportunity framing is needed.
---

# TH Hot Questions

1. Confirm normalized data exists:
   - `data/normalized/<period>/<pack_type>/`
2. Run baseline analysis:
   - `python scripts/analyze/hot_questions.py --pack-dir data/normalized/<period>/<pack_type> --question "<question>"`
   - optional scoring config: `--scoring-config data/context/hot_questions_scoring.default.json`
   - required for Blake-mode quality: `--use-llm-postprocess --require-llm-attempt --strict-narrative --challenge-card-mode`
   - optional historical calibration: `--use-historical-context` or `--historical-context <path>`
3. Return challenge-card default format:
   - 3-5 key bullets
   - one compact table
   - risks, opportunities, actions
   - 5 challenge cards (2 C&US, 1 Canada, 1 US, 1 LE watchout)
   - compatibility hot-questions list derived from cards
   - close with: `Is there any specific questions you'd like help coming up with an answer for?`
4. If confidence is low, provide provisional answer and ask one clarifying question.

## Required Behaviors
1. Use evidence references from normalized artifacts only.
2. Do not over-explain methods unless asked.
3. Keep wording direct and useful for time-constrained executive review.
4. Explicitly call out `lineage_degraded` conditions when present.
5. Always include scorecard fields:
   - `score_total`
   - `score_band`
   - `dimension_scores`
   - `confidence_reason`
6. Variance questions must be metric-specific with numeric deltas, prioritizing `vs Budget` and `vs LE`.
7. Use supplementary tokenized workbooks to draft explanation evidence where available.
8. Each non-watchout card must include at least one narrative evidence reference from slide text blocks.
9. Do not use bridge-only evidence for causal claims; bridge slides are numeric anchors only.
10. If narrative support is weak or LLM postprocess fails, output deterministic cards with explicit downgrade warning.

## Helper
Run:
- `python skills/th-hot-questions/scripts/run_hot_questions.py --pack-dir data/normalized/<period>/<pack_type> --question "<question>"`

See `references/output_format.md` for strict response template.
