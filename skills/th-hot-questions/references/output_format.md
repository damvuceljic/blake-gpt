# Challenge Card Output Format

Default output shape:

1. Key insights (3-5 bullets)
2. Compact table:
   - Metric
   - Observation
   - Implication
3. Risks (max 3)
4. Opportunities (max 3)
5. Actions (max 3)
6. Challenge cards (5 total for close packs):
   - 2 C&US cards
   - 1 Canada card
   - 1 US card
   - 1 LE watchout card
7. Compatibility section:
   - `anticipated_hot_questions` derived from challenge cards
8. End prompt:
   - `Is there any specific questions you'd like help coming up with an answer for?`

Each non-watchout card must include:
- `metric`
- `region`
- `challenge_question`
- `prepared_answer`
- `why_now`
- `basis_summary` (`vs_budget`, `vs_le`, `mom`, `qoq`, `yoy`)
- `narrative_evidence_refs`
- `supplementary_evidence_refs`
- `confidence`
- `verify_next`

Quality rules:
- No bridge-only causal claims.
- At least one narrative evidence ref per non-watchout card.
- Budget or LE basis required per non-watchout card.
- If confidence is medium/low, include uncertainty and one concrete verification step.
