# Blake Mode Intent Map

Skill-token requirement:
1. Blake prompts must start with one of:
   - `$th-intake-router`
   - `$th-hot-questions`
   - `$th-deck-proofing`
   - `$th-variance-watch`
   - `$th-blake-mode`

Keywords to intent:

1. `ingest`, `intake`, `new files`, `process month` -> `ingest`
2. `hot questions`, `top risks`, `executive brief` -> `hot_questions`
3. `proof`, `proofing`, `review deck` -> `proofing`
4. `variance`, `bridge integrity`, `reconcile` -> `variance_watch`
5. `compare`, `prior month`, `month-over-month` -> `compare`

Default fallback:
1. `hot_questions`
