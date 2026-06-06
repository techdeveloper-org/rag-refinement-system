# TODO-15 - PhaseF security audit

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-15",
  "title": "PhaseF security audit",
  "phase": "F",
  "parallel_group": "F",
  "depends_on": [
    "TODO-14"
  ],
  "status": "pending",
  "agents": [
    "threat-modeling-specialist",
    "sast-engineer",
    "secrets-detection-specialist",
    "dependency-vulnerability-analyst",
    "api-security-auditor",
    "auth-security-specialist",
    "penetration-tester",
    "infrastructure-security-auditor",
    "crypto-security-specialist",
    "security-compliance-mapper",
    "security-lead-auditor"
  ],
  "produces": [
    "docs/phase-F-security/security_audit_report.md"
  ],
  "gate": "security-lead-auditor APPROVED; ALL finding counts = 0",
  "stop_point": null,
  "context_file": "todos/todo-15-phasef-security-audit.md",
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
AGENT: threat-modeling-specialist
Phase: F.1 (BLOCKING — defines scope for F.2–F.5)
Parallel With: NONE
Depends On: Phase D GATE passed; devops-engineer F.0 staging provisioned
Context Budget: 10,000 tokens | Sources: [hld_v3.md, openapi.yaml, router-path, owasp-llm-top10]
Thinking Level: HIGH | budget_tokens: 10,000
Thinking Override: Rule 3 (adversarial + LLM attack surface)
Hallucination Risk: MEDIUM — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 10,000 tokens. Do not request or reference context outside this budget.
Thinking configured at HIGH (budget_tokens: 10,000). Set because LLM/RAG threat modeling is adversarial and spans STRIDE/PASTA plus the OWASP LLM Top-10. Reason within this budget.

OBJECTIVE: Produce the STRIDE/PASTA threat model + full attack-surface map of the RAG system, extended with the OWASP LLM Top-10 for the router/generation path. Defines scope for F.2–F.5. BLOCKING.

AGREED CONTRACTS:
- Treat document text + user query as untrusted. Threat-model router prompt-injection (role separation, strict-JSON output validation, reject non-JSON), RAG corpus poisoning (ingestion content checks), and embedding-inversion on stored chunks (Qdrant access control).
- Trust boundaries + data-classification tiers shared with solution-architect.
- (cyber-mathematics-expert auto-invoked for CVSS/FAIR/ALE.)

INSTRUCTIONS: Enumerate threats across ingestion, router, retrieval, generation, API, storage, and infra. RETRY LOOP: ALL threat counts (CRITICAL/HIGH/MEDIUM/LOW/INFO) → 0 before F.2; any >0 → return to Phase B → re-run F.1.

OUTPUT FORMAT: threat model + attack-surface map + scoped checklist driving F.2 (static), F.3 (API/auth), F.4 (infra/crypto), F.5 (compliance).

CONSTRAINTS: Zero-tolerance — no threat of any severity survives to F.2. Re-state the untrusted-input boundary at end.
===================================================================

===================================================================
AGENT: security-lead-auditor
Phase: F.6 (BINARY verdict gate — blocks Phase G)
Parallel With: NONE
Depends On: F.1–F.5 complete
Context Budget: 20,000 tokens | Sources: [f1-f5-findings, cvss-vectors, openapi.yaml, hld_v3.md]
Thinking Level: XHIGH | budget_tokens: 20,000
Thinking Override: Rule 2 role default (security-lead-auditor XHIGH — full risk aggregation)
Hallucination Risk: MEDIUM — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 20,000 tokens. Do not request or reference context outside this budget.
Thinking configured at XHIGH (budget_tokens: 20,000). Set because aggregating all F.1–F.5 findings into a CVSS risk matrix + final verdict is deep cross-domain synthesis. Reason within this budget.

OBJECTIVE: Aggregate ALL F.1–F.5 findings, assign CVSS v3.1 scores, build the risk matrix, and issue the final Security Audit Report with a BINARY verdict. (cyber-mathematics-expert auto-invoked for CVSS v3.1 vector math + FAIR + ALE.)

INSTRUCTIONS:
1. Collect findings from threat-modeling-specialist (F.1), sast/secrets/deps (F.2), api/auth/pentest (F.3), infra/crypto (F.4), compliance-mapper (F.5).
2. Score each with CVSS v3.1; build the risk matrix.
3. Verdict: APPROVED only when ALL finding counts = 0 (Critical=0, High=0, Medium=0, Low=0, Info=0). Any finding → REJECTED → itemized list returned to Phase B implementers → fix → re-run the affected F-phase → re-run F.6.
4. RETRY LOOP until all counts = 0.

OUTPUT FORMAT: Security Audit Report + risk matrix + BINARY verdict. Feeds Phase E (RS computation).

CONSTRAINTS: No deploy approval with ANY finding of ANY severity. No partial credit. Re-state: APPROVED requires every severity count = 0.
===================================================================

## Predecessor artifacts to load as input
- TODO-14 -> IEEE 829 plan, test suites, coverage report
