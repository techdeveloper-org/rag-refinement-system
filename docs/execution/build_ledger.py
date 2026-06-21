"""Generate a resumable execution ledger + per-TODO context packets.

Reads docs/orchestration_prompt.md and slices it into self-contained TODO
packets (each carrying only its relevant agent prompt(s) + shared context).
Preserves existing TODO status on re-run so it is safe for resume.

ASCII-only source (cp1252 safe). All file IO is explicit UTF-8.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ...\rag-refinement-system\docs
ROOT = os.path.dirname(ROOT)  # project root
SRC = os.path.join(ROOT, "docs", "orchestration_prompt.md")
EXEC = os.path.join(ROOT, "docs", "execution")
TODOS = os.path.join(EXEC, "todos")
os.makedirs(TODOS, exist_ok=True)

with open(SRC, encoding="utf-8") as f:
    text = f.read()
lines = text.split("\n")


def slice_section(start_sub, end_sub):
    s = text.find(start_sub)
    if s < 0:
        return ""
    e = text.find(end_sub, s + 1) if end_sub else len(text)
    if e < 0:
        e = len(text)
    return text[s:e].rstrip()


# --- extract delimited agent blocks ---
delim = [i for i, l in enumerate(lines) if set(l.strip()) == {"="} and len(l.strip()) >= 10]
blocks = []
for a, b in zip(delim[0::2], delim[1::2]):
    body = lines[a + 1:b]
    agent_line = next((x for x in body if x.startswith("AGENT:")), "")
    phase_line = next((x for x in body if x.startswith("Phase:")), "")
    blocks.append({"agent": agent_line, "phase": phase_line, "text": "\n".join(lines[a:b + 1])})


def find_block(name_sub, phase_sub=None):
    for blk in blocks:
        if name_sub in blk["agent"] and (phase_sub is None or phase_sub in blk["phase"]):
            return blk["text"]
    return None


def find_row(prefix):
    for l in lines:
        if l.startswith(prefix):
            return l.strip()
    return None


# shared context slices
common_parts = [
    slice_section("## STEP 0", "## PRE-FLIGHT"),
    slice_section("## CONSTRAINTS", "## ORCHESTRATION INSTRUCTIONS"),
    slice_section("## ARCHITECTURE DECISION RECORDS", "## TEAM ALIGNMENT REPORT"),
    slice_section("## TEAM ALIGNMENT REPORT", "## PHASE EXECUTION PLAN"),
    slice_section("## ENFORCEMENT RULES", "# PART 2"),
]
common = "\n\n---\n\n".join(p for p in common_parts if p)

# --- TODO definitions (dependency DAG + parallel groups) ---
SPEC = {
    "1.5": "pipelines/api-contract-pipeline/GREENFIELD_GUIDE.md",
    "2": "pipelines/joint-blueprint-validation-pipeline/GREENFIELD_GUIDE.md",
    "3": "pipelines/ui-ux-design-pipeline/STANDARD_PATH.md",
    "4": "pipelines/fullstack-validation-pipeline/FULLSTACK_VALIDATION_PIPELINE.md",
    "5": "pipelines/blueprint-documentation-pipeline/BLUEPRINT_DOCUMENTATION_PIPELINE.md",
    "6": "pipelines/sprint-planning-pipeline/GREENFIELD_GUIDE.md",
    "7": "pipelines/agent-task-routing-pipeline/GREENFIELD_GUIDE.md",
    "8": "pipelines/pre-implementation-alignment-pipeline/GREENFIELD_GUIDE.md",
}

todos = []


def add(tid, title, phase, pgroup, deps, agents, produces, gate, stop, blocks_list=None, row_prefix=None, spec=None):
    fname = tid.lower() + "-" + title.lower().replace(" ", "-").replace("/", "-").replace("+", "").replace(":", "")
    fname = "-".join([p for p in fname.split("-") if p])[:60] + ".md"
    todos.append({
        "meta": {
            "id": tid, "title": title, "phase": phase, "parallel_group": pgroup,
            "depends_on": deps, "status": "pending", "agents": agents,
            "produces": produces, "gate": gate, "stop_point": stop,
            "context_file": "todos/" + fname, "completed_artifacts": [],
        },
        "blocks": blocks_list or [],
        "row": find_row(row_prefix) if row_prefix else None,
        "spec": spec,
        "file": fname,
    })


add("TODO-00", "Phase0 refresh PRD and RnD brief", "0", "P0", [],
    ["business-analyst-agent", "product-manager-agent", "research-strategist", "technology-scout-analyst", "business-development-agent"],
    ["PRD.md", "docs/phase-0-requirements/phase1_architect_brief.md"],
    "NLI=1.0 + FactScore=1.0 before handoff", "User reviews refreshed PRD",
    blocks_list=[b for b in [find_block("business-analyst-agent", "0")] if b])

add("TODO-01", "Phase1 solution architecture HLD", "1", "P1", ["TODO-00"],
    ["solution-architect", "consensus-agent", "context-engineering-agent"],
    ["docs/phase-1-architecture/hld.md"],
    "consensus BINARY APPROVED (zero open items)", "User APPROVED HLD",
    blocks_list=[b for b in [find_block("solution-architect")] if b])

add("TODO-02", "Phase1.5 API contract OpenAPI", "1.5", "P1.5", ["TODO-01"],
    ["solution-architect", "python-backend-engineer", "api-testing-engineer", "integration-testing-engineer", "business-analyst-agent", "consensus-agent"],
    ["docs/phase-1-api-contracts/openapi.yaml", "docs/phase-1-api-contracts/fr_api_traceability.json"],
    "API CONTRACT APPROVED; 100% FR->operationId; DPDP x-pii/erasure", "User reviews openapi.yaml",
    row_prefix="| **1.5", spec=SPEC["1.5"])

add("TODO-03", "Phase2 joint blueprint validation", "2", "P2", ["TODO-02"],
    ["business-analyst-agent", "product-manager-agent", "solution-architect", "consensus-agent", "hallucination-detector"],
    ["docs/phase-2-validation/advisory_items.json"],
    "JOINT APPROVED", "User reviews advisory items",
    row_prefix="| **2 ", spec=SPEC["2"])

add("TODO-04", "Phase3 UIUX design standard path", "3", "P3", ["TODO-03"],
    ["ui-ux-designer", "consensus-agent", "hallucination-detector"],
    ["docs/phase-3-design/wireframes", "docs/phase-3-design/tokens_css.css", "docs/phase-3-design/accessibility_report.json"],
    "DESIGN APPROVED; APCA Lc>=60 body", "User reviews design",
    row_prefix="| **3 ", spec=SPEC["3"])

add("TODO-05", "Phase4 fullstack reconciliation", "4", "P4", ["TODO-04"],
    ["business-analyst-agent", "product-manager-agent", "solution-architect", "ui-ux-designer", "consensus-agent", "hallucination-detector", "context-faithfulness-engineer"],
    ["docs/phase-4-reconciliation/hld_v3.md", "docs/phase-4-reconciliation/grand_advisory_items.json"],
    "GRAND BLUEPRINT APPROVED", "User reviews grand blueprint",
    row_prefix="| **4 ", spec=SPEC["4"])

add("TODO-06", "Phase5 SRS and UML documentation", "5", "P5", ["TODO-05"],
    ["business-analyst-agent", "product-manager-agent", "uml-structural-diagram-engineer", "uml-behavioral-diagram-engineer", "uml-interaction-diagram-engineer", "drawio-diagram-architect", "mermaid-diagram-engineer", "hallucination-detector", "context-faithfulness-engineer", "consensus-agent"],
    ["SRS.md", "uml/", "drawio/", "docs/phase-5-documentation/drawio_urls.json"],
    "DOCUMENTATION APPROVED; SRS FR->PRD traceable", "User reviews SRS + UML",
    row_prefix="| **5 ", spec=SPEC["5"])

add("TODO-07", "Phase6 sprint planning github", "6", "P6", ["TODO-06"],
    ["scrum-master-agent", "agile-tooling-specialist", "business-analyst-agent", "product-manager-agent", "solution-architect", "ui-ux-designer", "consensus-agent"],
    ["docs/phase-6-sprint-planning/sprint_verdict.json", "docs/phase-6-sprint-planning/sprint_agent_briefs.json"],
    "SPRINT READY; 100% FR->story", "User reviews sprint board",
    row_prefix="| **6 ", spec=SPEC["6"])

add("TODO-08", "Phase7 agent task routing", "7", "P7", ["TODO-07"],
    ["orchestrator-agent", "agile-business-mathematics-expert", "context-engineering-agent", "prompt-generation-expert", "hallucination-detector", "context-faithfulness-engineer", "reliability-auditor", "security-testing-engineer", "consensus-agent"],
    ["docs/phase-7-routing/implementation_execution_plan.json", "docs/phase-7-routing/ar2_dag_proof.json", "docs/phase-7-routing/ar3_context_windows.json"],
    "ROUTING APPROVED; RS=1.0; STOP 7", "STOP 7 user review",
    row_prefix="| **7 ", spec=SPEC["7"])

add("TODO-09", "Phase8 pre implementation alignment", "8", "P8", ["TODO-08"],
    ["business-analyst-agent", "product-manager-agent", "solution-architect", "scrum-master-agent", "prompt-generation-expert", "context-engineering-agent", "hallucination-detector", "context-faithfulness-engineer", "reliability-auditor", "consensus-agent"],
    ["docs/phase-8-alignment/implementation_execution_plan_v2.json", "docs/phase-8-alignment/ir5_alignment_verdict.json"],
    "IMPLEMENTATION READY; RS=1.0; STOP 8", "STOP 8 user review",
    row_prefix="| **8 ", spec=SPEC["8"])

add("TODO-10", "PhaseB1 foundation schema and ops", "B1", "B1", ["TODO-09"],
    ["database-engineer", "devops-engineer"],
    ["migrations/", "infra/", "Dockerfile", "docker-compose.yml", "CI workflow"],
    "unit tests pass per component", None,
    blocks_list=[b for b in [find_block("database-engineer"), find_block("devops-engineer", "Group B1")] if b])

add("TODO-11", "PhaseB2 ingestion router api", "B2", "B2", ["TODO-10"],
    ["data-engineer", "ai-engineer", "prompt-generation-expert", "python-backend-engineer"],
    ["ingestion module", "LangGraph router module", "FastAPI services"],
    "unit tests pass per component", None,
    blocks_list=[b for b in [find_block("data-engineer"), find_block("ai-engineer (paired"), find_block("python-backend-engineer")] if b])

add("TODO-12", "PhaseB3 frontend personal tool", "B3", "B3", ["TODO-11"],
    ["react-engineer", "ui-ux-designer"],
    ["frontend/ React SPA"],
    "unit tests pass; UI renders citations + confidence + explainability", None,
    blocks_list=[b for b in [find_block("react-engineer (paired")] if b])

add("TODO-13", "PhaseC hallucination gate", "C", "C", ["TODO-11", "TODO-12"],
    ["hallucination-detector", "context-faithfulness-engineer"],
    ["detection report", "faithfulness scorecard"],
    "NLI=1.0 AND FactScore=1.0 (retry loop)", None,
    blocks_list=[b for b in [find_block("hallucination-detector")] if b])

add("TODO-14", "PhaseD QA pipeline", "D", "D", ["TODO-13"],
    ["test-management-agent", "unit-testing-specialist", "integration-testing-engineer", "e2e-testing-engineer", "api-testing-engineer", "performance-testing-engineer", "ai-model-testing-engineer", "data-quality-testing-engineer"],
    ["IEEE 829 plan", "test suites", "coverage report"],
    "coverage=100% AND DRE=1.0", None,
    blocks_list=[b for b in [find_block("test-management-agent")] if b])

add("TODO-15", "PhaseF security audit", "F", "F", ["TODO-14"],
    ["threat-modeling-specialist", "sast-engineer", "secrets-detection-specialist", "dependency-vulnerability-analyst", "api-security-auditor", "auth-security-specialist", "penetration-tester", "infrastructure-security-auditor", "crypto-security-specialist", "security-compliance-mapper", "security-lead-auditor"],
    ["docs/phase-F-security/security_audit_report.md"],
    "security-lead-auditor APPROVED; ALL finding counts = 0", None,
    blocks_list=[b for b in [find_block("threat-modeling-specialist"), find_block("security-lead-auditor")] if b])

add("TODO-16", "PhaseE reliability gate", "E", "E", ["TODO-13", "TODO-14", "TODO-15"],
    ["reliability-auditor"],
    ["reliability report", "RS value"],
    "RS = 1.0 (retry loop, no deploy below 1.0)", None,
    blocks_list=[b for b in [find_block("reliability-auditor")] if b])

add("TODO-17", "PhaseG deploy and README refresh", "G", "G", ["TODO-16"],
    ["devops-engineer", "cloud-security-architect"],
    ["prod deploy config", "LangSmith monitoring", "README.md"],
    "RS=1.0 satisfied; healthchecks green", "User reviews live deploy",
    blocks_list=[b for b in [find_block("devops-engineer (paired")] if b])

# --- preserve existing status on resume ---
ledger_path = os.path.join(EXEC, "ledger.json")
existing = {}
if os.path.exists(ledger_path):
    with open(ledger_path, "r", encoding="utf-8") as f:
        old = json.load(f)
    existing = {x["id"]: x for x in old.get("todos", [])}

for t in todos:
    m = t["meta"]
    if m["id"] in existing:
        m["status"] = existing[m["id"]].get("status", "pending")
        m["completed_artifacts"] = existing[m["id"]].get("completed_artifacts", [])


# --- write packets ---
def write_packet(t):
    m = t["meta"]
    out = []
    out.append("# " + m["id"] + " - " + m["title"])
    out.append("")
    out.append("> Self-contained execution packet. All context below is sliced from")
    out.append("> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,")
    out.append("> team alignment, enforcement rules) is in ../_common_context.md.")
    out.append("")
    out.append("## Metadata")
    out.append("```json")
    out.append(json.dumps(m, indent=2))
    out.append("```")
    out.append("")
    out.append("## Dispatch instruction (hand this packet to orchestrator-agent)")
    out.append("")
    out.append("Act as **orchestrator-agent**. Execute this TODO using the embedded agent")
    out.append("prompt(s) below plus the shared context in ../_common_context.md. Honor the")
    out.append("dependencies, gate, and STOP point in Metadata. Produce every artifact listed")
    out.append("in Metadata.produces. Math masters are auto-invoked, never sequenced directly.")
    out.append("")
    out.append("Checkpoint protocol (REQUIRED for resume):")
    out.append("1. Before starting: set this TODO status to \"in_progress\" in ../ledger.json.")
    out.append("2. After artifacts are verified on disk: set status to \"done\" and fill")
    out.append("   completed_artifacts.")
    out.append("3. If a STOP point is defined: set status \"awaiting_user\" and pause.")
    out.append("4. If interrupted/rate-limited mid-run: leave status \"in_progress\"; on resume")
    out.append("   this TODO re-runs from scratch (make writes idempotent).")
    out.append("")
    if t["blocks"]:
        out.append("## Embedded agent prompt(s) from the bundle")
        for blk in t["blocks"]:
            out.append("")
            out.append(blk)
        out.append("")
    if t["row"]:
        out.append("## Phase roster + pipeline spec (from Part 1 pre-processing table)")
        out.append("")
        out.append(t["row"])
        out.append("")
        out.append("Follow the pipeline spec: `" + (t["spec"] or "") + "`")
        out.append("Run the listed lead agents per that spec; enforce the gate and STOP point above.")
        out.append("This phase has no standalone agent block in the bundle by design - it is a")
        out.append("self-contained sub-pipeline launched from its spec file.")
        out.append("")
    out.append("## Predecessor artifacts to load as input")
    if m["depends_on"]:
        for dep in m["depends_on"]:
            dmeta = next((x["meta"] for x in todos if x["meta"]["id"] == dep), None)
            if dmeta:
                out.append("- " + dep + " -> " + ", ".join(dmeta["produces"]))
    else:
        out.append("- None (entry TODO). Input baseline: existing PRD.md + README.md at project root.")
    out.append("")
    with open(os.path.join(TODOS, t["file"]), "w", encoding="utf-8") as f:
        f.write("\n".join(out))


for t in todos:
    write_packet(t)

# --- write shared common context ---
with open(os.path.join(EXEC, "_common_context.md"), "w", encoding="utf-8") as f:
    f.write("# Shared Context (sliced from docs/orchestration_prompt.md)\n\n"
            "Every TODO packet references this file. It carries the KG header, constraints,\n"
            "ADRs, team-alignment AGREED CONTRACTS, and enforcement rules that apply to all agents.\n\n"
            "---\n\n" + common + "\n")

# --- write ledger ---
ledger = {
    "project": "RAG Refinement System",
    "source_prompt": "docs/orchestration_prompt.md",
    "generated": "2026-06-06",
    "kg": {"agents": 250, "skills": 428, "domains": 48, "math_masters": 23,
           "edges": 4210, "version": "29.9.16", "built": "2026-06-06"},
    "resume_procedure": [
        "1. Read docs/execution/ledger.json.",
        "2. Find the first TODO with status != 'done'/'awaiting_user' whose depends_on are all 'done'.",
        "3. Open its context_file under docs/execution/.",
        "4. Hand that packet to orchestrator-agent (it embeds the per-agent prompt(s)).",
        "5. Set status 'in_progress' before starting; 'done' after artifacts verified; 'awaiting_user' at a STOP.",
        "6. TODOs in the same parallel_group with satisfied deps may run concurrently.",
        "7. On rate limit: just stop. The ledger already holds the last state. Resume at step 1.",
    ],
    "legend": {"status": ["pending", "in_progress", "done", "awaiting_user", "blocked"]},
    "todos": [t["meta"] for t in todos],
}
with open(ledger_path, "w", encoding="utf-8") as f:
    json.dump(ledger, f, indent=2)

# --- summary ---
print("Ledger + packets generated.")
print("TODOs:", len(todos))
print("Agent blocks extracted from bundle:", len(blocks))
miss = [t["meta"]["id"] for t in todos if not t["blocks"] and not t["row"]]
print("TODOs with neither block nor row (check):", miss)
for t in todos:
    nb = len(t["blocks"])
    tag = ("row" if t["row"] else ("%d block(s)" % nb if nb else "EMPTY"))
    print("  ", t["meta"]["id"], "|", t["meta"]["status"], "|", t["meta"]["phase"], "|", tag, "->", t["file"])
