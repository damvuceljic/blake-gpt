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
   - optional postprocess: `--use-llm-postprocess`
   - optional historical calibration: `--use-historical-context` or `--historical-context <path>`
3. Return default executive format:
   - 3-5 key bullets
   - one compact table
   - risks, opportunities, actions
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

## Helper
Run:
- `python skills/th-hot-questions/scripts/run_hot_questions.py --pack-dir data/normalized/<period>/<pack_type> --question "<question>"`

See `references/output_format.md` for strict response template.
