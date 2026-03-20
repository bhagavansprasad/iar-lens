# oic-lens — Master Plan + Window Handoff Document
**Version:** 2.1
**Last updated:** March 2026
**Purpose:** Single source of truth for oic-lens. Paste this entire file at
the start of every new Claude window.
**Public Repository:** https://github.com/bhagavansprasad/oic-lens.git

---

## How to Use This Document

At the start of every new Claude window, paste this file as your first message with:
> *"This is the master plan for oic-lens. We are currently working on
> Milestone [X]. The handoff block is at the bottom."*

Also paste `oic_resource_file_reference.md` alongside this document.

At the end of every milestone, run:
```bash
python tools/capture_context.py --milestone M2 --label 32-33
```
Review `output/context_M2.md`, fill in Open Questions and Exact Next Action,
then update the Handoff Block at the bottom of this file.

---

## Project Summary

**What we are building:** A generic 3-step pipeline that takes any two OIC
`.car` or `.iar` files and produces a review report for architects and
business stakeholders. The tool acts as an architect assistant — it identifies
what changed, recommends improvements, flags security issues, and produces
a structured review checklist.

**Why we are building it:** Currently the only way to review an OIC integration
change is to manually open both versions in OIC and read through the entire
flow. This tool automates that.

**LLM:** Gemini (Google) via `google-generativeai`
**Agent framework:** LangGraph
**Language:** Python 3.11+

---

## Core Design Principle: LLM as Architect

The LLM is the architect. The tool's job is to give the LLM everything it
needs to reason — not to pre-filter what is significant.

- Step 1 is pure Python — deterministic, zero LLM
- Step 2 gives the LLM a structured inventory upfront, then serves file
  content on demand when the LLM requests it
- The tool only excludes files with provably zero semantic value
- The LLM decides what is significant, what is a risk, what needs review

**LLM receives upfront (the inventory map):**
```json
{
  "integration": {
    "code": "ALTERA_CREATE_SO_INTEGRAT",
    "source_version": "01.00.0032",
    "target_version": "01.00.0033",
    "processors": [
      {"id": "processor_964", "type": "contentBasedRouter",
       "name": "Router_964", "has_resources": true}
    ],
    "connections": [
      {"code": "ALTERA_ATP", "adapter": "atpdatabase",
       "security_policy": "JDBC_OVER_SSL"}
    ]
  },
  "delta": {
    "new_steps": [...],
    "removed_steps": [...],
    "modified_steps": [...]
  }
}
```

**LLM requests files on demand:**
```
LLM: "Read processor_964 expr.properties from both versions"
Agent: fetches and returns content
LLM: reasons about the change
```

---

## The Three-Step Pipeline

The pipeline has exactly 3 steps. Milestones are sub-tasks within each step.
This is the fixed structure — it never changes.

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: EXTRACT AND DIFF                                        │
│                                                                 │
│  Input:  Two .car / .iar files                                  │
│  Output: {label}_delta.json                                     │
│  LLM:    None — pure Python                                     │
│                                                                 │
│  ├── M1: Structural delta (new + removed processors)           │
│  ├── M2: Modified steps detection (file content diff)          │
│  └── M3: Flow understander (LLM summary of the full diff)      │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼ {label}_delta.json
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: AGENT INVESTIGATION                                     │
│                                                                 │
│  Input:  {label}_delta.json + extracted workspace files         │
│  Output: {label}_report.json + {label}_flow_context.json        │
│  LLM:    Yes — Gemini via LangGraph                             │
│                                                                 │
│  └── M4: LangGraph agent — inventory map + on-demand file reads│
└─────────────────────────────────────────────────────────────────┘
         │
         ▼ {label}_report.json + {label}_flow_context.json
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: REPORT GENERATION                                       │
│                                                                 │
│  Input:  {label}_delta.json + report.json + flow_context.json   │
│  Output: {label}_change_report.md                               │
│  LLM:    Minimal — narrative sections only                      │
│                                                                 │
│  └── M5: Report generator (markdown + architect checklist)     │
└─────────────────────────────────────────────────────────────────┘

Cross-cutting:
  M6 — End-to-end integration test (all 3 steps wired + validated)
  M7 — Hardening (error handling, --dry-run, multi-pair test)
  M8 — Security review (*.wsdl, *.jca, *.xsd — deferred)
```

---

## Three Categories of Change

### Category 1: New Processors
Processor ID exists in target but not source.
→ Read files from target workspace.
→ LLM: what does this step do, why was it added, any risks?

### Category 2: Removed Processors
Processor ID exists in source but not target.
→ Read files from source workspace.
→ LLM: what did this step do, what is the impact of removing it?

### Category 3: Modified Processors ← MOST CRITICAL
Same processor ID in BOTH versions, but file content differs.
→ Read files from BOTH workspaces.
→ LLM: what specifically changed, is this an improvement or a risk?

**The proof this matters — processor_964:**
In v32→v33, processor_964 (contentBasedRouter) existed in both versions.
Its routing condition changed silently:
- v32: `Status = 'Awaiting Shipping'`
- v33: `Status = 'Awaiting Shipping' OR varCount >= '11'`
This adds a retry cap of 11 — addresses an infinite loop risk. The most
important change in the entire diff. A tool that only detects new/removed
processors misses this entirely.

---

## File Structure

```
oic-lens/
├── README.md
├── config.py                      ← all settings (paths, model, flags)
├── requirements.txt
├── .gitignore
├── run_batch.py                   ← batch orchestrator
├── oic_resource_file_reference.md ← file type reference (carry into every window)
├── flow-dump/                     ← input CAR/IAR files (gitignored)
├── workspace/                     ← extraction workspace (gitignored)
├── output/                        ← generated reports (gitignored)
├── tools/
│   ├── discover_file_types.py     ← surveys file types across all pairs
│   ├── inspect_unknowns.py        ← reads content of unknown file types
│   └── capture_context.py         ← generates window handoff package
└── src/
    ├── extractor.py               ← REUSED: extracts CAR/IAR, finds project.xml
    ├── file_reader.py             ← REUSED: reads files, lists processor files
    │
    │   ── Step 1 ──────────────────────────────────────────────
    ├── flow_compare.py            ← M1+M2: parse project.xml, structural delta,
    │                                        calls file_diff for modified detection
    ├── file_diff.py               ← M2: file-level content diff
    ├── flow_understander.py       ← M3: LLM summary of full diff
    ├── iar_compare.py             ← Step 1 orchestrator → delta.json
    │
    │   ── Step 2 ──────────────────────────────────────────────
    ├── agent_state.py             ← M4: LangGraph state schema
    ├── agent_prompts.py           ← M4: prompts for all 3 change categories
    ├── agent.py                   ← M4: LangGraph agent
    │
    │   ── Step 3 ──────────────────────────────────────────────
    └── report_generator.py        ← M5: markdown report + architect checklist
```

---

## Ground Truth: v32 → v33 (Validation Case)

All checks verified directly from raw CAR extraction.

### Integration Facts
- Code: `ALTERA_CREATE_SO_INTEGRAT`
- Purpose: Automates Sales Order creation — receives trigger from MASON,
  enriches from ATP database, creates SO in Oracle Cloud via REST, handles
  ship-to address via SOAP, sends email notifications at each milestone
  and error condition.
- v32: `01.00.0032` — **71 flow processors** (74 total including infrastructure)
- v33: `01.00.0033` — **79 flow processors** (82 total including infrastructure)
- Infrastructure types excluded from count: `integrationMetadata`,
  `messageTracker`, `globalVariableDefinition` — these carry no business
  logic and never change meaningfully between versions.

### New Processors in v33 (8 total)
| processor_id | type | what it does |
|---|---|---|
| processor_11623 | assignment | Initialises `varCount = 0` (retry counter) |
| processor_11630 | assignment | Initialises `varStatus = ''` (status variable) |
| processor_11643 | assignment | Sets `varStatus` from `getSOLineStatus` response |
| processor_11649 | assignment | Increments `varCount + 1` |
| processor_11655 | contentBasedRouter | Routes on `varStatus = 'Awaiting Shipping'` |
| processor_11739 | notification | Notification9 — SO lines not Awaiting Shipping |
| processor_11974 | contentBasedRouter | Routes on `count(Shipment) > 0` |
| processor_12068 | notification | Notification10 — no delivery number returned |

### Removed Processors in v33
None — 0 removed.

### Modified Processors in v33 (at minimum)
| processor_id | type | what changed |
|---|---|---|
| processor_964 | contentBasedRouter | Condition: `Status = 'Awaiting Shipping'` → `Status = 'Awaiting Shipping' OR varCount >= '11'` |

---

## Validation Checklist

Organised by pipeline step and milestone.

### Step 1 — Extract and Diff

| Check | Expected | Milestone | Status |
|---|---|---|---|
| Source flow processor count | 71 | M1 | ✅ PASS |
| Target flow processor count | 79 | M1 | ✅ PASS |
| New steps count | 8 | M1 | ✅ PASS |
| New processor IDs correct | 11623, 11630, 11643, 11649, 11655, 11739, 11974, 12068 | M1 | ✅ PASS |
| Removed steps count | 0 | M1 | ✅ PASS |
| processor_964 in modified_steps | Yes | M2 | ⬜ PENDING |
| processor_964 old condition | `Status = 'Awaiting Shipping'` | M2 | ⬜ PENDING |
| processor_964 new condition | `Status = 'Awaiting Shipping' OR varCount >= '11'` | M2 | ⬜ PENDING |
| No stateinfo false positives in modified_steps | Yes | M2 | ⬜ PENDING |
| flow_context.json mentions modified steps | Yes | M3 | ⬜ PENDING |
| flow_context.json mentions processor_964 condition change | Yes | M3 | ⬜ PENDING |

### Step 2 — Agent Investigation

| Check | Expected | Milestone | Status |
|---|---|---|---|
| report.json contains modified_steps section | Yes | M4 | ⬜ PENDING |
| report.json describes processor_964 condition change | Yes | M4 | ⬜ PENDING |
| report.json assigns risk to processor_964 | medium minimum | M4 | ⬜ PENDING |

### Step 3 — Report Generation

| Check | Expected | Milestone | Status |
|---|---|---|---|
| change_report.md has Modified Steps section | Yes | M5 | ⬜ PENDING |
| change_report.md shows processor_964 before/after | Yes | M5 | ⬜ PENDING |
| change_report.md has Architect Review Checklist | Yes | M5 | ⬜ PENDING |
| processor_964 appears in checklist | Yes | M5 | ⬜ PENDING |

---

## Milestones

### M0 — Project Bootstrap ✅ DONE
**Step:** Pre-pipeline scaffolding
Repo created, reused files copied, extractor smoke test passing.

---

### M1 — Structural Delta ✅ DONE
**Step 1 sub-task:** New + removed processor detection

**Built:**
- `src/flow_compare.py` — redesigned, LCS algorithm, 3 category slots
- `src/iar_compare.py` — Step 1 orchestrator, writes `{label}_delta.json`
- `tests/test_m1_structural_delta.py` — 137/137 passing across 11 pairs

**CLI:** `python src/iar_compare.py 32-33`

---

### M2 — Modified Steps Detection ⬜ IN DESIGN
**Step 1 sub-task:** File content diff for common processors

**What to build:**

`src/file_diff.py`
- `find_resources_dir(extract_path)` → finds `resources/` dir in workspace
- `detect_modified(src_res, tgt_res, common_ids, processor_meta)` → list of modified processors
- For each common processor:
  - Collect files, skip `is_excluded()` and `is_deferred()`
  - Normalise paths: strip `resourcegroup_{ID}`, preserve `output_{ID}`
  - Handle XSL hash change: one `req_*.xsl` each side → treat as modified
  - Compare content: normalise `stitch.json` by JSON key-sort before comparing
  - Return raw old + new content per changed file
- Output per modified processor:
  `{processor_id, type, name, changed_files[{key, old_content, new_content}]}`

`src/flow_compare.py` — extend `compute_delta()`
- Add optional `source_extract_path`, `target_extract_path` args
- Call `file_diff.detect_modified()` when paths provided
- Populate `modified_steps` in delta output

`{label}_delta.json` — updated schema:
```json
{
  "modified_steps": [
    {
      "processor_id": "processor_964",
      "type": "contentBasedRouter",
      "name": "Router_964",
      "changed_files": [
        {
          "key": "output_966/expr.properties",
          "old_content": "TextExpression : Status = 'Awaiting Shipping'\n...",
          "new_content": "TextExpression : Status = 'Awaiting Shipping' OR varCount >= '11'\n..."
        }
      ]
    }
  ]
}
```

`tests/test_m2_modified_steps.py`
- Assert processor_964 in modified_steps
- Assert old condition correct
- Assert new condition correct
- Assert no stateinfo false positives

**CLI:** `python tests/test_m2_modified_steps.py 32-33`

---

### M3 — Flow Understander ⬜ PENDING
**Step 1 sub-task:** LLM summary of the full diff

`src/flow_understander.py`
- Receives full delta (new + removed + modified)
- Builds inventory map for LLM
- Python-computed `systems_involved` — do NOT ask LLM for this
- LLM prompt explicitly includes modified steps count and details
- Output: `{label}_flow_context.json`

**Test:** flow_context.json mentions processor_964 condition change.

---

### M4 — Agent Investigation ⬜ PENDING
**Step 2:** LangGraph agent

`src/agent_state.py` — `modified_steps` as first-class field
`src/agent_prompts.py` — three prompts (new / removed / modified)
`src/agent.py` — LangGraph graph:
```
INIT → BUILD_INVENTORY → INVESTIGATE → SYNTHESIZE → END
```
- `build_inventory_node`: sends structured map to LLM upfront
- `investigate_node`: LLM requests files on demand; modified steps read
  from BOTH versions; modified steps default risk: `medium` minimum
- `synthesize_node`: findings across all three categories

**Test:** report.json contains modified_steps with processor_964 described.

---

### M5 — Report Generator ⬜ PENDING
**Step 3:** Markdown report

`src/report_generator.py`
Report section order:
```
1.  Header
2.  What This Integration Does
3.  What Changed
4.  Full Flow Diagram (Mermaid)
5.  Executive Summary (risk + recommendation)
6.  Statistics
7.  New Steps
8.  Modified Steps          ← NEW
9.  Removed Steps
10. Key Observations
11. Architect Review Checklist  ← NEW
12. Approval Conditions
```
- Modified steps: before/after table per changed file
- Checklist: `- [ ] processor_964 (Router) — verify retry cap of 11`
- Salvage from old code: `_trim_purpose`, `_trim_impact`, Mermaid generation

**Test:** change_report.md has Modified Steps + Checklist with processor_964.

---

### M6 — End-to-End Integration Test ⬜ PENDING
**Cross-cutting:** Wire all 3 steps

- Wire Step 1 → Step 2 → Step 3 in `run_batch.py`
- Run full pipeline on 32-33
- All validation checklist items must pass

---

### M7 — Hardening ⬜ PENDING
**Cross-cutting:** Production readiness

- Error handling: missing files, LLM failures, malformed XML
- `--dry-run` flag: Step 1 only, no LLM cost, for quick structural checks
- Test against a second pair beyond 32-33

---

### M8 — Security Review ⬜ PENDING (future)
**Cross-cutting:** Deferred capability

- Enable `is_deferred()` files: `*.wsdl`, `*.jca`, `*.xsd`
- LLM reviews adapter contracts for security policy changes
- New report section: Security Findings

---

## Resource File Classification (Quick Reference)

Full reference: `oic_resource_file_reference.md` (carry into every window).

```python
def is_excluded(filename):
    """Provably zero semantic value — never sent to LLM, never diffed."""
    if filename.endswith("stateinfo.json"):   return True  # UI designer state
    if filename.endswith("_stateinfo.xml"):   return True  # XSL mapper UI state
    if filename.endswith(".dvm"):             return True  # PII, out of scope
    if filename == "nxsdmetadata.properties": return True  # always empty
    if filename == "oic_project.properties":  return True  # internal hash
    if filename == "project.yaml":            return True  # timestamps only
    if filename.endswith(".zip"):             return True  # binary
    return False

def is_deferred(filename):
    """LLM-readable but not in scope until M8 security review milestone."""
    if filename.endswith(".wsdl"):  return True
    if filename.endswith(".jca"):   return True
    if filename.endswith(".xsd"):   return True
    return False
```

**XSL hash filename rule:** If source has one `req_*.xsl` and target has one
`req_*.xsl` for the same processor, treat as modified — not removed + added.

**Path normalisation:** Strip `resourcegroup_{ID}`, preserve `output_{ID}`.

---

## Key Facts About project.xml

```
Namespaces:
  ns3 = "http://www.oracle.com/2014/03/ics/project"
  ns2 = "http://www.oracle.com/2014/03/ics/flow/definition"

Key elements:
  <ns3:icsproject>
    <projectCode>          ← integration code
    <projectVersion>       ← version string e.g. 01.00.0033
    <ns3:icsflow>
      <ns2:application>    ← external connection
        <ns2:role>         ← "source" or "target"
        <ns2:adapter>
          <ns2:code>       ← connection code e.g. ALTERA_ATP
          <ns2:name>       ← operation name
      <ns2:processor>      ← one per flow step
        <ns2:type>         ← assignment | transformer | contentBasedRouter |
                              notification | for | while | catch | catchAll |
                              wait | stitch | activityStreamLogger
        <ns2:processorName>
      <ns2:orchestration>
        <ns2:invoke>
          name attr        ← display name
          refUri attr      ← points to application_id
```

**Processor ID is stable across versions.** Use it as the matching key.

**Processor naming priority:**
1. `<ns2:processorName>` if present
2. `<invoke name="...">` from orchestration
3. Fall back to `{TypeLabel}_{numeric_id}` e.g. `Router_964`

**Skip types (infrastructure — excluded from flow processor count):**
`integrationMetadata`, `messageTracker`, `globalVariableDefinition`

---

## Design Decisions Log

**LLM as architect, not whitelist** (March 2026)
The tool does not pre-filter what the LLM sees. Only files with provably
zero semantic value are excluded. The LLM receives an inventory map upfront
and requests file contents on demand.

**Exclude DVM lookup files** (March 2026)
`lookups/*.dvm` — out of scope. Contains PII (email addresses).

**Defer *.wsdl, *.jca, *.xsd to M8** (March 2026)
LLM-readable but require a dedicated security review milestone with
appropriate prompts. Including prematurely adds noise without structure.

**XSL hash filename — treat as modified not removed+added** (March 2026)
OIC generates new content hash when XSL changes. Naive diff loses
before/after context. One XSL each side for same processor = modified.

**stitch.json — JSON key-sort normalisation** (March 2026)
OIC reorders JSON keys with no semantic change. Sort before comparing
to suppress false positives.

**Two path depth variants** (March 2026)
Shallow: `processor_{ID}/resourcegroup_{RG}/{file}` — most types
Deep: `processor_{ID}/output_{OUT}/resourcegroup_{RG}/{file}` — router branches
`output_{ID}` is stable across versions. Must be preserved in normalised key.

**Flow processor count is 71→79, not 74→82** (March 2026)
The 74→82 figure in original master plan counted infrastructure processor
types (`integrationMetadata`, `messageTracker`, `globalVariableDefinition`).
These carry no business logic. Correct flow processor count is 71→79.

---

## Context Capture Process (End of Every Milestone)

### Step 1 — Run the script
```bash
python tools/capture_context.py --milestone M2 --label 32-33
```

### Step 2 — Review the output
Open `output/context_M2.md` and verify:
- All function signatures are correct
- All design decisions are recorded
- Validation results match what you observed
- Next action is specific enough to start without context

### Step 3 — Update this document
Fill in the Handoff Block below and save.

The generated package contains:
- Milestone summary + API snapshots
- Design decisions log
- Validation results (run automatically)
- Full content of `oic_resource_file_reference.md` (embedded)

---

## HANDOFF BLOCK — Update at end of every milestone

### Completed milestones
- M0 ✅ — Project bootstrap
- M1 ✅ — Structural delta, 67/67 tests passing
- M2 ✅ — Modified steps detection, 29/29 tests passing
- M3 ✅ — Flow understander, 23/23 tests passing, 69/69 full regression

### Current milestone
**M4 — Agent Investigation — PENDING**

### Current branch
`feature/m4-agent-investigation`

### Open questions
_Update this section manually before saving._

### Exact next action
Rewrite src/agent.py, src/agent_state.py, src/agent_prompts.py per M4 spec. Check existing files first — they may have salvageable scaffolding like M3 did.