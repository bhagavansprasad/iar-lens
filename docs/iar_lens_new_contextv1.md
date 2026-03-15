# oic-lens — Master Plan + Window Handoff Document
**Version:** 1.0
**Last updated:** This planning session (March 2026)
**Purpose:** Single source of truth for oic-lens. Paste this entire file at the start of every new Claude window.

---

## How to Use This Document

At the start of every new Claude window, paste this file as your first message with:
> *"This is the master plan for oic-lens. We are currently working on Milestone [X]. The handoff block is at the bottom."*

At the end of every window, update the **Handoff Block** at the bottom before saving.

---

## Project Summary

**What we are building:** A generic 3-step pipeline that takes any two OIC `.car` or `.iar` files and produces a review report for architects and business stakeholders.

**Why we are building it:** Currently the only way to review an OIC integration change is to manually open both versions in OIC and read through the entire flow. This tool automates that.

**LLM:** Gemini (Google) via `google-generativeai`
**Agent framework:** LangGraph
**Language:** Python 3.11+

---

## The Three-Step Pipeline

This is the fixed structure. Milestones build each step incrementally but the pipeline never changes.

```
Step 1: EXTRACTOR
  Input:  Two .car / .iar files
  Does:   Extracts both ZIPs, parses project.xml, computes structural delta
          (new processors, removed processors, modified processors)
  Output: {label}_delta.json

Step 2: COMPARE AND UNDERSTAND
  Input:  {label}_delta.json + extracted workspace files
  Does:   LangGraph agent reads files for changed processors,
          LLM analyses what changed and why, produces findings
  Output: {label}_report.json + {label}_flow_context.json

Step 3: REPORT GENERATION
  Input:  {label}_delta.json + {label}_report.json + {label}_flow_context.json
  Does:   Assembles a structured markdown report with business summary,
          technical detail, and architect review checklist
  Output: {label}_change_report.md
```

---

## Foundation Decision (Agreed)

**Approach: Hybrid — reuse specific files, redesign the rest**

| File | Decision | Reason |
|---|---|---|
| `extractor.py` | **Reuse as-is** | Correctly handles CAR/IAR, multi-project.xml selection by processor count |
| `file_reader.py` | **Reuse as-is** | Works correctly, good file type metadata |
| `run_batch.py` | **Reuse as-is** | Orchestration logic is correct |
| `flow_compare.py` | **Redesign fresh** | Structural debt — was designed around new/removed only; modified_steps must be first-class from the start |
| `iar_agent.py` | **Redesign fresh** | build_reading_list_node hardcodes new/removed only; needs redesign not patching |
| `iar_agent_prompts.py` | **Redesign fresh** | Missing modified-step prompt entirely |
| `report_generator.py` | **Redesign fresh** | Missing modified-steps section; redesign cleaner than patching |
| `flow_understander.py` | **Redesign fresh** | Must be aware of modified steps from the start |
| `iar_agent_state.py` | **Redesign fresh** | State schema needs modified_steps as first-class field |

**What to salvage from redesigned files (don't throw away):**
- LCS algorithm from `flow_compare.py` — correct, keep it
- Python-computed `systems_involved` pattern from `flow_understander.py` — do not ask LLM for this
- `_trim_purpose` and `_trim_impact` helpers from `report_generator.py` — good, keep them
- Mermaid diagram generation from `report_generator.py` — keep it
- `FILE_TYPE_ROLES` dict from `file_reader.py` — useful reference

---

## Critical Design Requirement: Three Categories of Change

This is the most important thing the new solution must get right. The existing solution only handles categories 1 and 2. Category 3 is what the existing solution misses.

### Category 1: New Processors
Processor ID exists in target (v33) but not source (v32).
→ Read files from target workspace, ask LLM what this step does and why it was added.

### Category 2: Removed Processors
Processor ID exists in source (v32) but not target (v33).
→ Read files from source workspace, ask LLM what this step did and the impact of removing it.

### Category 3: Modified Processors ← THE CRITICAL GAP
Same processor ID exists in BOTH versions, but file content differs.
→ Read files from BOTH workspaces, ask LLM what specifically changed and why it matters.

**The proof this matters — the `processor_964` case:**
In the v32→v33 diff, `processor_964` (a Content-Based Router) existed in both versions.
Its routing condition changed silently:
- v32: `Status = 'Awaiting Shipping'`
- v33: `Status = 'Awaiting Shipping' OR varCount >= '11'`

This adds a retry cap of 11 — it addresses an infinite loop risk. It is arguably the most
important change in the entire diff. The existing solution cannot detect it because
processor_964 is neither new nor removed. The new solution must catch this.

---

## Ground Truth: v32 → v33 (Our Validation Case)

These facts were verified directly from raw CAR file extraction — not from documents.
Use this checklist to validate each milestone.

### Integration Facts
- Integration name: `ALTERA_CREATE_SO_INTEGRAT`
- v32 version: `01.00.0032` (74 processors)
- v33 version: `01.00.0033` (82 processors)
- Integration purpose: Automates Sales Order creation — receives trigger from MASON system,
  enriches from ATP database, creates SO in Oracle Cloud via REST, handles ship-to address
  via SOAP, sends email notifications at each milestone and error condition.

### New Processors in v33 (8 total)
| processor_id | type | what it does |
|---|---|---|
| processor_11623 | assignment | Initialises `varCount = 0` (retry counter) |
| processor_11630 | assignment | Initialises `varStatus = ''` (status variable) |
| processor_11643 | assignment | Sets `varStatus` from `getSOLineStatus` response |
| processor_11649 | assignment | Increments `varCount + 1` |
| processor_11655 | contentBasedRouter | If `varStatus = 'Awaiting Shipping'` → pick wave; else → Notification9 |
| processor_11739 | notification | Notification9 — alert when SO lines not in Awaiting Shipping status |
| processor_11974 | contentBasedRouter | If `count(Shipment) > 0` → proceed; else → Notification10 |
| processor_12068 | notification | Notification10 — alert when no delivery number returned |

### Removed Processors in v33
None — 0 removed.

### Modified Processors in v33 (at minimum)
| processor_id | type | what changed |
|---|---|---|
| processor_964 | contentBasedRouter | Condition changed from `Status = 'Awaiting Shipping'` to `Status = 'Awaiting Shipping' OR varCount >= '11'` |

### Validation Checklist
| Check | Expected | Milestone |
|---|---|---|
| New steps count | 8 | M1 |
| New processor IDs | 11623, 11630, 11643, 11649, 11655, 11739, 11974, 12068 | M1 |
| Removed steps count | 0 | M1 |
| Modified steps: processor_964 detected | Yes | M2 |
| processor_964 old condition | `Status = 'Awaiting Shipping'` | M2 |
| processor_964 new condition | `Status = 'Awaiting Shipping' OR varCount >= '11'` | M2 |
| flow_context mentions modified steps | Yes | M3 |
| report.json has modified_steps section | Yes | M4 |
| change_report.md has Modified Steps section | Yes | M5 |
| Architect checklist in report | Yes | M5 |

---

## File Structure

```
oic-lens/
├── README.md
├── config.py                  ← all settings (paths, model, flags)
├── requirements.txt
├── run_batch.py               ← batch orchestrator (reused)
├── .gitignore
├── flow-dump/                 ← input CAR/IAR files (gitignored)
│   └── 32-33/
│       ├── FACTORYDOCK-TEST-32.car
│       └── FACTORYDOCK-TEST-33.car
├── workspace/                 ← extraction workspace (gitignored)
├── output/                    ← generated reports (gitignored)
└── src/
    ├── extractor.py           ← REUSED: extracts CAR/IAR, finds project.xml
    ├── file_reader.py         ← REUSED: reads files, lists processor files
    ├── flow_compare.py        ← REDESIGNED: parse + delta (all 3 categories)
    ├── file_diff.py           ← NEW: file-level content diff for modified detection
    ├── flow_understander.py   ← REDESIGNED: LLM flow context (modified-aware)
    ├── agent_state.py         ← REDESIGNED: state schema with modified_steps
    ├── agent_prompts.py       ← REDESIGNED: prompts for all 3 change categories
    ├── agent.py               ← REDESIGNED: LangGraph agent (3-category reading list)
    └── report_generator.py    ← REDESIGNED: report with modified steps + checklist
```

---

## Key Facts About OIC project.xml Structure

Critical for anyone implementing the parsers.

```
Namespaces:
  ns3 = "http://www.oracle.com/2014/03/ics/project"
  ns2 = "http://www.oracle.com/2014/03/ics/flow/definition"

Key elements:
  <ns3:icsproject>              ← root
    <projectCode>               ← integration code / name
    <projectVersion>            ← version string e.g. 01.00.0033
    <projectDescription>        ← human description (changes between versions!)
    <ns3:icsflow>
      <ns2:application>         ← external connection (one per adapter)
        <ns2:role>              ← "source" or "target"
        <ns2:adapter>
          <ns2:code>            ← connection code e.g. ALTERA_ATP
          <ns2:name>            ← operation name e.g. updateDeliveryNumber
      <ns2:processor>           ← one per flow step
        <ns2:type>              ← assignment | transformer | notification |
                                   contentBasedRouter | for | while | catch |
                                   catchAll | notification | wait | stitch |
                                   globalVariableDefinition | activityStreamLogger
        <ns2:processorName>     ← human name (only set for some types)
        <ns2:processorDescription> ← description (usually empty)
      <ns2:orchestration>       ← the actual flow sequence
        <ns2:invoke>            ← external call node
          name attribute        ← display name e.g. "Oracle ATP9", "REST2"
          refUri attribute      ← points to application_id
```

**Processor ID is stable across versions.** Use it as the matching key, not the step name.

**Processor naming priority:**
1. `<ns2:processorName>` if present
2. `<invoke name="...">` from orchestration if the processor is an invoke
3. Fall back to `{type}_{numeric_id}` e.g. `Router_964`

---

## Key Facts About Resource Files

```
Path pattern:
  resources/processor_{ID}/resourcegroup_{ID}/{filename}

Important file types:
  expr.properties      ← routing conditions, variable expressions — HIGH VALUE
                          Contains: TextExpression, XpathExpression, VariableName
  req_{hash}.xsl       ← XSLT transformation logic — HIGH VALUE
  notification_body.data    ← email HTML body — MEDIUM VALUE
  notification_subject.data ← email subject line — MEDIUM VALUE
  notification_to.data      ← recipient addresses — MEDIUM VALUE
  stateinfo.json       ← UI designer state — IGNORE (noise)
  *.wsdl / *.xsd / *.jca   ← adapter contracts — LOW VALUE

Noise suppression rule:
  resourcegroup IDs change between versions even when content is identical.
  Compare FILE CONTENT, not file paths, to detect real changes.
  Strip resourcegroup_ID from paths before comparing.
```

---

## Milestones

### M0 — Project Bootstrap
**Branch:** `main` (initial commit)
**Builds:** Step — scaffolding

What to build:
- Create repo `oic-lens`
- Copy reused files: `src/extractor.py`, `src/file_reader.py`, `run_batch.py`
- Create `config.py`, `requirements.txt`, `README.md`, `.gitignore`
- Verify: `python src/extractor.py` extracts a CAR file without errors

Dependencies: `google-generativeai`, `langgraph`, `python-dotenv`

Test: Extract both v32 and v33 CAR files, confirm `project.xml` found in each.
PR: `M0: Project bootstrap`

---

### M1 — Step 1a: Structural Delta (New + Removed)
**Branch:** `feature/m1-structural-delta`
**Builds:** Step 1 (partial)

What to build:
- `src/flow_compare.py` — redesigned fresh
  - `extract_steps(project_xml_path)` → returns metadata + ordered processor list + applications
  - `compute_delta(source_data, target_data)` → returns new_steps, removed_steps (modified_steps added in M2)
  - Matching key: `processor_id` (stable across versions), NOT step name
  - Keep LCS algorithm for positionally_shifted detection
  - Processor naming priority: processorName → invoke name → type_id fallback
- `src/iar_compare.py` — orchestrates Step 1, writes `{label}_delta.json`

Test: Run v32→v33, confirm exactly 8 new steps with correct processor IDs, 0 removed.
PR: `M1: Step 1a — structural delta new/removed steps`

---

### M2 — Step 1b: Modified Steps Detection ⭐ MOST CRITICAL
**Branch:** `feature/m2-modified-steps`
**Builds:** Step 1 (completes it)

What to build:
- `src/file_diff.py` — new file, core of this milestone
  - For each processor present in BOTH versions: locate its files in both workspaces
  - Normalise paths: strip version string and resourcegroup IDs before comparing
  - Compare content for: `expr.properties`, `*.xsl`, `notification_*.data`
  - Suppress noise: identical content despite different resourcegroup IDs → unchanged
  - Return: list of modified processors, each with processor_id, type, name,
    and list of changed files with old_content + new_content
- Extend `flow_compare.py`: call `file_diff.py`, add `modified_steps` to delta output
- Update `{label}_delta.json` schema to include `modified_steps`

Key decisions:
- Content comparison: exact string match after stripping whitespace — no fuzzy matching
- Store full old and new content in delta — Phase 2 needs both
- `expr.properties` and `*.xsl` always trigger modified flag; `stateinfo.json` never does

Test: Run v32→v33, confirm processor_964 appears in modified_steps with correct old/new condition.
PR: `M2: Step 1b — modified steps detection`

---

### M3 — Step 1c: Flow Understander
**Branch:** `feature/m3-flow-understander`
**Builds:** Step 1 (adds LLM understanding layer)

What to build:
- `src/flow_understander.py` — redesigned, modified-step aware
  - Feeds new + removed + modified steps into LLM prompt
  - Keeps Python-computed `systems_involved` (do not ask LLM for this)
  - Keeps `change_type` classification
  - Output: `{label}_flow_context.json`

Prompt must include: "X existing steps had their logic changed (in addition to Y new steps)"

Test: flow_context.json mentions the condition change on processor_964, not just 8 new steps.
PR: `M3: Step 1c — flow understander modified-step aware`

---

### M4 — Step 2: Agent Investigation
**Branch:** `feature/m4-agent`
**Builds:** Step 2

What to build:
- `src/agent_state.py` — redesigned, modified_steps as first-class state field
- `src/agent_prompts.py` — redesigned, three prompts:
  - `format_new_step_prompt()` — what does this new step do, why was it added
  - `format_removed_step_prompt()` — what did this step do, impact of removal
  - `format_modified_step_prompt()` — what specifically changed, is this improvement or bug
- `src/agent.py` — redesigned LangGraph agent
  - Graph: INIT → BUILD_READING_LIST → INVESTIGATE → SYNTHESIZE → END
  - `build_reading_list_node`: includes all three categories
  - `investigate_node`: for modified steps, reads BOTH versions' files
  - `synthesize_node`: produces findings across all three categories
  - Modified steps default risk: `medium` minimum — silent change to existing logic

Test: report.json contains modified_steps section with processor_964 condition change described.
PR: `M4: Step 2 — agent investigation with modified steps`

---

### M5 — Step 3: Report Generator
**Branch:** `feature/m5-report`
**Builds:** Step 3

What to build:
- `src/report_generator.py` — redesigned
  - Salvage: `_trim_purpose`, `_trim_impact`, Mermaid diagram generation
  - Add: Modified Steps section
  - Add: Architect Review Checklist (checkboxes, processor IDs, what to verify)

Report section order:
```
1. Header
2. What This Integration Does        ← from flow_context, plain English
3. What Changed                      ← from flow_context, plain English
4. Full Flow Diagram                 ← Mermaid
5. Executive Summary                 ← risk + recommendation
6. Statistics
7. New Steps
8. Modified Steps                    ← NEW SECTION
9. Removed Steps
10. Key Observations
11. Architect Review Checklist       ← NEW SECTION
12. Approval Conditions
```

Modified steps format: before/after table per changed file showing old value → new value.
Checklist format: `- [ ] processor_964 (Router) — verify retry cap of 11 is correct threshold`

Test: change_report.md has Modified Steps section showing processor_964 condition change.
PR: `M5: Step 3 — report generator with modified steps and checklist`

---

### M6 — End-to-End Integration Test
**Branch:** `feature/m6-integration`
**Builds:** Pipeline wiring

What to build:
- Wire all three steps in `run_batch.py`
- Run full pipeline on v32→v33
- Validate against ground truth checklist (all 10 checks must pass)
- Fix any integration issues

Test: All 10 items in Ground Truth Validation Checklist pass.
PR: `M6: End-to-end integration test`

---

### M7 — Hardening
**Branch:** `feature/m7-hardening`
**Builds:** Production readiness

What to build:
- Error handling for missing files, LLM failures, malformed XML
- `--dry-run` flag: runs Step 1 only, no LLM cost, for quick structural checks
- Test against a second version pair from the batch list

PR: `M7: Hardening — error handling and multi-pair validation`

---

## HANDOFF — Updated after baseline analysis

### Baseline established
Existing iar-lens output for 32-33 has been reviewed. Key findings:
- modified_steps: NOT present in delta.json — confirmed gap
- processor_964 condition change: NOT in report — confirmed missing
- Step counts wrong: tool reports 72→80, actual is 74→82 (2 skipped per version)
- Node names: generic fallbacks (Assign_11623 not meaningful)
- Business impact descriptions: repetitive/vague due to LLM anchoring on flow_context
- No architect checklist

### What "better" means for this project
The new solution beats the baseline if:
1. processor_964 appears in a modified_steps section with old/new condition shown
2. Step counts match actual processor counts (74→82)
3. Node names use expression content where available
4. Each step's business impact is specific to that step, not generic
5. An architect checklist is present with specific processor IDs

### Current milestone
M0 — Not started. Repo is iar-lens on GitHub.
New repo oic-lens should be created fresh.

### Exact next action
Create oic-lens repo, copy extractor.py + file_reader.py + run_batch.py,
create config.py / requirements.txt / README.md / .gitignore,
test extraction of both CAR files.