# Execution Runbook — RAG Refinement System

This folder turns `docs/orchestration_prompt.md` into a **resumable, TODO-driven build**.
If a rate limit (or anything) stops you, you lose nothing: `ledger.json` always holds the
last state, and every TODO packet is self-contained.

## Files

| File | Role |
|------|------|
| `ledger.json` | **Durable source of truth.** Every TODO with status + deps + artifacts. Resume reads this. |
| `_common_context.md` | Shared context (KG header, constraints, ADRs, team-alignment contracts, enforcement rules) sliced once from the prompt. Referenced by every packet. |
| `todos/*.md` | One self-contained packet per TODO: metadata + dispatch instruction + the embedded per-agent prompt(s) (or phase spec) sliced from the prompt. |
| `build_ledger.py` | Regenerates packets from the prompt. **Preserves existing status** on re-run (safe to run anytime). |

## How to run (or resume)

1. Open `ledger.json`.
2. Pick the first TODO whose `status` is `pending` and whose every `depends_on` is `done`.
   - TODOs that share a `parallel_group` and have satisfied deps can run **concurrently**.
3. Open its `context_file` (under `todos/`).
4. Hand that packet to **orchestrator-agent** (it embeds the per-agent prompts to use).
5. Status transitions the orchestrator must write back to `ledger.json`:
   - `in_progress` before starting
   - `done` after artifacts are verified on disk
   - `awaiting_user` when the TODO has a `stop_point` (user review gate)
   - `blocked` if it cannot proceed
6. Repeat from step 1.

**Rate-limit resume:** just stop. On the next session, run step 1 again. Anything left
`in_progress` re-runs from scratch (writes are idempotent), so a half-finished TODO is safe.

To re-slice packets after editing the prompt: `python docs/execution/build_ledger.py`
(your statuses are preserved).

## Dependency graph (execution order)

```
TODO-00 (Phase 0  refresh PRD)         [STOP: review PRD]
  -> TODO-01 (Phase 1  HLD)            [STOP: APPROVED]
  -> TODO-02 (Phase 1.5 API contract)  [STOP]
  -> TODO-03 (Phase 2  joint validate) [STOP]
  -> TODO-04 (Phase 3  UI/UX)          [STOP]
  -> TODO-05 (Phase 4  reconciliation) [STOP]
  -> TODO-06 (Phase 5  SRS + UML)      [STOP]
  -> TODO-07 (Phase 6  sprint plan)    [STOP]
  -> TODO-08 (Phase 7  routing)        [STOP 7]
  -> TODO-09 (Phase 8  alignment)      [STOP 8]
  -> TODO-10 (Phase B1  schema+ops) ----+--- parallel within group
  -> TODO-11 (Phase B2  ingest+router+api)  (after B1)
  -> TODO-12 (Phase B3  frontend)           (after B2)
  -> TODO-13 (Phase C  hallucination gate)  (after B2+B3)
  -> TODO-14 (Phase D  QA)                  (after C)
  -> TODO-15 (Phase F  security)            (after D)
  -> TODO-16 (Phase E  reliability RS=1.0)  (after C+D+F)
  -> TODO-17 (Phase G  deploy + README)     [STOP]
```

## Notes
- Pre-processing phases 0-8 each end at a **user STOP** (the pipeline specs mandate review).
  So the build advances one phase per approval until Phase B, where B1/B2 internals parallelize.
- Math masters (mathematics-engineer, anti-hallucination-mathematician, etc.) are **auto-invoked**
  by specialists — they are never separate TODOs.
- The harness task list mirrors these TODOs for live visibility, but `ledger.json` is authoritative.
