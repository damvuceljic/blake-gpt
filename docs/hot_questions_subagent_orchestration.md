# Hot Questions Subagent Orchestration (Phase 2 Design)

## Purpose
Define the phase-2 orchestration pattern for evidence-gap resolution and quality assurance of hot-question cards.

## Scope
1. Analyst subagent pass per evidence gap and supplementary workbook target.
2. Auditor subagent validation pass over analyst proposals.
3. Deterministic merge/escalation behavior with explicit failure handling.

## Orchestration Flow
1. Runtime generates deterministic base cards plus `evidence_gap_registry`.
2. Orchestrator spawns one analyst task per actionable gap:
   - Inputs: metric context, current card text, citation bundle, targeted workbook scope.
   - Output: proposed narrative delta, updated citations, confidence delta, verify-next note.
3. Auditor tasks validate each analyst proposal:
   - Check policy compliance (term guard, restaurant-first scope, preview==LE semantics).
   - Check citation integrity (path/location/excerpt substance).
   - Check no synthetic claims beyond provided evidence.
4. Merger applies approved updates to card payload:
   - Keep deterministic base as source of truth.
   - Apply only auditor-approved patches.
   - Preserve audit trail per card (`proposal_id`, `auditor_status`, `rejection_reason`).
5. If all proposals rejected, return original deterministic cards with insufficiency callout.

## Subagent Contracts
### Analyst Agent
1. Input:
   - `metric`
   - `card_payload`
   - `evidence_gap_entry`
   - `supplementary_scope`
2. Output:
   - `candidate_question`
   - `candidate_answer`
   - `candidate_citation_bundle`
   - `confidence_delta`
   - `assumption_log`

### Auditor Agent
1. Input:
   - Analyst output payload
   - Policy snapshot
   - Original deterministic card
2. Output:
   - `approved` boolean
   - `violations` list
   - `recommended_patch` (if approved)

## Merge and Escalation Rules
1. Merge only when auditor marks `approved=true`.
2. If violation count > 0, reject patch and preserve original deterministic text.
3. If card coverage remains below policy minimum after orchestration:
   - Return available cards unchanged.
   - Emit explicit insufficiency notice.
4. Escalate to human review when:
   - repeated policy violations across >=2 cards,
   - missing LE semantics reconciliation,
   - citation validation fails for all proposals.

## Failure Handling
1. Analyst timeout/failure:
   - mark gap as `analyst_unavailable`;
   - keep deterministic card.
2. Auditor timeout/failure:
   - treat as non-approved;
   - keep deterministic card and append warning.
3. Merge failure:
   - rollback to deterministic payload snapshot;
   - return warning with failed patch IDs.

## Observability
1. Track per-run counters:
   - `analyst_tasks_total`
   - `analyst_tasks_success`
   - `auditor_approvals`
   - `auditor_rejections`
   - `cards_patched`
2. Persist a compact audit log under `data/analysis/<period>/<pack_type>/hot_questions_orchestration_audit.json`.
