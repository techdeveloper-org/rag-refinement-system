# TODO-00 - Phase0 refresh PRD and RnD brief

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-00",
  "title": "Phase0 refresh PRD and RnD brief",
  "phase": "0",
  "parallel_group": "P0",
  "depends_on": [],
  "status": "pending",
  "agents": [
    "business-analyst-agent",
    "product-manager-agent",
    "research-strategist",
    "technology-scout-analyst",
    "business-development-agent"
  ],
  "produces": [
    "PRD.md",
    "docs/phase-0-requirements/phase1_architect_brief.md"
  ],
  "gate": "NLI=1.0 + FactScore=1.0 before handoff",
  "stop_point": "User reviews refreshed PRD",
  "context_file": "todos/todo-00-phase0-refresh-prd-and-rnd-brief.md",
  "completed_artifacts": []
}
```

## Dispatch instruction (hand this packet to orchestrator-agent)

Act as **orchestrator-agent**. Execute this TODO using the embedded agent
prompt(s) below plus the shared context in ../_common_context.md. Honor the
dependencies, gate, and STOP point in Metadata. Produce every artifact listed
in Metadata.produces. Math masters are auto-invoked, never sequenced directly.

Checkpoint protocol (REQUIRED for resume):
1. Before starting: set this TODO status to "in_progress" in ../ledger.json.
2. After artifacts are verified on disk: set status to "done" and fill
   completed_artifacts.
3. If a STOP point is defined: set status "awaiting_user" and pause.
4. If interrupted/rate-limited mid-run: leave status "in_progress"; on resume
   this TODO re-runs from scratch (make writes idempotent).

## Embedded agent prompt(s) from the bundle

===================================================================
AGENT: business-analyst-agent (+ product-manager-agent, research-strategist, technology-scout-analyst, business-development-agent)
Phase: 0 — BA/PM + R&D (Mode A Greenfield)
Parallel With: research agents parallel; BA/PM sequential on their output
Depends On: NONE (entry phase)
Context Budget: 12,000 tokens | Sources: [existing-PRD.md, existing-README.md, market-research-delta]
Thinking Level: HIGH | budget_tokens: 10,000
Thinking Override: Rule 2 role default (BA/PM HIGH)
Hallucination Risk: HIGH — verified by hallucination-detector (NLI=1.0 + FactScore=1.0 before handoff)

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 12,000 tokens. Do not request or reference context outside this budget.
Thinking configured at HIGH (budget_tokens: 10,000). This level was set because requirements elicitation + AHP/MAUT prioritization + stakeholder-conflict resolution need multi-step reasoning. Reason within this budget.
Your output will be verified by hallucination-detector. Cite every factual claim (market figure, competitor capability) with its source.

OBJECTIVE: Run the BA/PM + R&D Greenfield pipeline (`pipelines/ba-pm-rnd-pipeline/GREENFIELD_GUIDE.md`) to REFRESH the existing `PRD.md` for the RAG Refinement System into a current, structured, sellable PRD/BRD — same product idea, updated content.

AGREED CONTRACTS:
- PRD remains append-aware: bump version (1.0 → 2.0), update Date/Status, add a "## Change Log" section, and move any superseded claim to a "Superseded" note rather than silently deleting it.
- Every FR becomes FR-NNN; every NFR becomes NFR-NNN; add WSJF scores, Kano classification, OKRs, BDD Gherkin acceptance, and an RTM skeleton.
- Add a DPDP Act 2023 compliance subsection (PII in uploaded docs, erasure/access endpoints, no-retention mode, India data residency) and a SOC2-readiness note for enterprise sales.
- Re-verify every market figure ($2.33B RAG market / 42.7% CAGR / 78% hallucination reduction / 40–70% token reduction) against a citable source; flag any that cannot be re-sourced as "unverified — needs source" rather than restating.

INPUT CONTEXT: The existing `PRD.md` (v1.0, 2026-03-21) and `README.md` are at project root — read them as the prior baseline. The product, two angles, three-stage pipeline, and tech stack are all defined there and remain the same idea.

INSTRUCTIONS:
1. Elicit + structure requirements into the 14-section PRD/BRD format from the guide.
2. product-manager-agent: WSJF backlog, Kano, OKRs, GTM, pricing validation (delegates AHP/WSJF math to ba-pm-mathematics-expert — auto-invoked).
3. research-strategist + technology-scout-analyst: refresh market sizing, competitive landscape, and tech-stack currency (LangGraph 1.0, embedding models) with citations (delegates meta-analysis/BM25 math to research-mathematics-expert — auto-invoked).
4. Pass through hallucination-detector + context-faithfulness-engineer until NLI=1.0 + FactScore=1.0.
5. Produce `phase1_architect_brief.md` (top-WSJF FRs, DPDP constraints, tech-stack signals, open architectural questions) for solution-architect.

OUTPUT FORMAT: Refreshed `PRD.md` at project root + artifacts under `docs/phase-0-requirements/`. STOP for user review of the refreshed PRD before Phase 1.

CONSTRAINTS: Same product idea — do not redesign the concept. Updated, sourced, structured. NLI=1.0 + FactScore=1.0 gate is mandatory before handoff.
===================================================================

## Predecessor artifacts to load as input
- None (entry TODO). Input baseline: existing PRD.md + README.md at project root.
