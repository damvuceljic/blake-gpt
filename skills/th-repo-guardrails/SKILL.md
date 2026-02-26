---
name: th-repo-guardrails
description: Enforce repository operating guardrails for the Blake Finance Copilot. Use when starting work in this repo, before finalizing changes, or when validating portability, data-governance boundaries, and concise CFO-facing output behavior.
---

# TH Repo Guardrails

1. Read `GUARDRAILS.md` before editing code or running analysis.
2. Keep all file and script references relative to repo root.
3. Run portability lint:
   - `python scripts/quality/check_portability.py`
4. Verify raw source files stay local and only normalized/redacted context is used for model calls.
5. Keep user-facing responses short, material, and action-oriented.

## Required Checks
1. Confirm required control files exist:
   - `GUARDRAILS.md`
   - `AGENTS.md`
   - `todo.md`
   - `AGENT_LESSONS.md`
2. Confirm monthly outputs stay in these folders:
   - `data/packs/<period>/<pack_type>/`
   - `data/normalized/<period>/<pack_type>/`
   - `data/analysis/<period>/<pack_type>/`
3. If `source_mode` is `offline_values`, require `lineage_degraded=true` in pack summary.

## Helper
Run:
- `python skills/th-repo-guardrails/scripts/guardrail_check.py`

See `references/checklist.md` for the completion checklist.
