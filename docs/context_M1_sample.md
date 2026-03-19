# oic-lens — Window Handoff Package
**Milestone:** M1 — Structural Delta — New + Removed Steps
**Status:** DONE
**Generated:** 2026-03-18 23:46 UTC
**Validation pair:** 32-33

> Paste this file into the next Claude window AFTER the master plan.
> It supplements the master plan — it does not replace it.

---

## Files Built or Modified This Milestone

- **src/flow_compare.py** (new) ✅
- **src/iar_compare.py** (new) ✅
- **tests/test_m1_structural_delta.py** (new) ✅

## Public API Snapshot

### `src/extractor.py`
- `def extract_iar(iar_path: str, workspace_dir: str) -> dict` — Extracts a .iar.zip file into the workspace directory.
- `def find_project_xml(root_dir: str) -> str | None` — Recursively searches for project.xml inside the extracted IAR/CAR folder.

### `src/file_diff.py`
- `def detect_modified(source_res_path: str, target_res_path: str, common_processor_ids: set, processor_meta: dict) -> list` — For each processor ID in common_processor_ids, compare resource file
- `def find_resources_dir(extract_path: str) -> Optional[str]` — Locate the resources/ directory inside an extracted workspace.

### `src/file_reader.py`
- `def read_file(file_path: str) -> dict` — Reads a single file from the IAR workspace and returns its content
- `def list_processor_files(processor_id: str, version: str = None) -> dict` — Lists all files associated with a given processor ID inside the workspace.
- `def list_all_processor_files(version: str) -> dict` — Lists all processor folders and their files for a given IAR version.

### `src/flow_compare.py`
- `def extract_steps(project_xml_path: str) -> dict` — Parse a project.xml and return structured metadata.
- `def compute_delta(source_data: dict, target_data: dict, source_extract_path: Optional[str] = None, target_extract_path: Optional[str] = None) -> dict` — Compare source (old) and target (new) extract_steps() results.

### `src/flow_understander.py`
- `def understand_flow(integration: str, version_from: str, version_to: str, source_data: dict, target_data: dict, delta: dict, output_dir: str, label: str = None) -> dict` — Calls the LLM with the full flow context of both versions and produces
- `def adapter_names(apps: list) -> list`

### `src/iar_agent.py`
- `def init_node(state: IARReviewAgentState) -> IARReviewAgentState` — Loads <label>_delta.json and <label>_flow_context.json, initializes all state fields.
- `def build_reading_list_node(state: IARReviewAgentState) -> IARReviewAgentState` — Pure Python node — builds a focused reading list of processors
- `def investigate_node(state: IARReviewAgentState) -> IARReviewAgentState` — For each processor in the reading list:
- `def synthesize_node(state: IARReviewAgentState) -> IARReviewAgentState` — Sends all findings + flow_context to LLM to produce the final
- `def create_iar_review_agent_graph()` — Build and compile the IAR Review Agent LangGraph.
- `def run_agent()` — Run the IAR Review Agent.

### `src/iar_agent_prompts.py`
- `def format_investigate_prompt(processor_id: str, step_name: str, step_type: str, status: str, version: str, files: List[Dict], file_contents: List[Dict], flow_context: Optional[Dict] = None) -> str` — Formats the INVESTIGATE_PROCESSOR_PROMPT with actual data.
- `def format_synthesize_prompt(integration: str, version_from: str, version_to: str, statistics: Dict, findings: List[Dict], shifted_steps: List[Dict], unchanged_steps: List[Dict], flow_context: Optional[Dict] = None) -> str` — Formats the SYNTHESIZE_REPORT_PROMPT with actual data.

### `src/iar_agent_state.py`
- `class IARReviewAgentState`

### `src/iar_compare.py`
- `def run_comparison(label = None, source_path = None, target_path = None)` — Extract source + target CAR/IAR files, compute delta, write {label}_delta.json.

### `src/report_generator.py`
- `def generate_report(delta_path: str = None, report_path: str = None, output_path: str = None) -> str`

### `src/run_batch.py`
- `def run_agent_sync()` — Sync wrapper around the async run_agent() for use in batch processing.
- `def run_batch()`

## Delta JSON Schema (live sample)

**Label:** 32-33
**Versions:** v01.00.0032 → v01.00.0033
**Processors:** 71 → 79
**New steps:** 8
**Removed steps:** 0
**Modified steps:** 0
**Top-level keys:** ['source_version', 'target_version', 'source_count', 'target_count', 'new_steps', 'removed_steps', 'modified_steps', 'positionally_shifted', 'label', 'source_extract_path', 'target_extract_path', 'integration_code', 'integration_name']

**new_steps[0] shape:**
```json
{
  "processor_id": "processor_11623",
  "type": "assignment",
  "name": "Assign_11623",
  "position": 74
}
```

_modified_steps is empty — M2 not yet complete._

## Validation Results

- ✅ Test suite: tests/test_m1_structural_delta.py `================================================================
M1 TEST — Structural Delta
Pairs: 1 of 11  (32-33)
======================================================================

  [32-33]
    ✅ PASS  v01.00.0032 -> v01.00.0033  |  new=8  removed=0  src_procs=71  tgt_procs=79

======================================================================
RESULTS: 17/17 passed  |  0 failed
======================================================================

✅  M1 PASSED — 1 pair(s) validated.`
- ✅ New steps count == 8 `Found 8: ['processor_11623', 'processor_11630', 'processor_11643', 'processor_11649', 'processor_11655', 'processor_11739', 'processor_11974', 'processor_12068']`
- ✅ New processor IDs correct `Missing: set()  Extra: set()`
- ✅ Removed steps count == 0 `Found 0`

## Design Decisions Log

### Session: March 2026 — Source Tree Analysis

**LLM as architect, not whitelist**
The tool does not pre-filter what the LLM sees. The LLM receives an inventory
map upfront and requests file contents on demand. Only files with provably
zero semantic value are excluded.

**Exclude DVM lookup files**
`lookups/*.dvm` — out of scope. Contains PII (email addresses).

**Defer *.wsdl, *.jca, *.xsd to security review milestone (M8)**
LLM-readable but not in M2-M7 scope. Requires dedicated milestone with
appropriate prompts.

**XSL hash filename — treat as modified not removed+added**
If source has one `req_*.xsl` and target has one `req_*.xsl` for the same
processor, treat as a single modification. OIC generates new hash on content
change — naive diff loses before/after context.

**stitch.json — JSON key-sort normalisation**
Sort keys before comparing. OIC reorders JSON keys with no semantic change.
Without this, produces false positives.

**Two path depth variants**
- Shallow: `processor_{ID}/resourcegroup_{RG}/{file}`
- Deep (router branches): `processor_{ID}/output_{OUT}/resourcegroup_{RG}/{file}`
Strip `resourcegroup_{ID}`, preserve `output_{ID}`.

**Exclusion rules**
```python
def is_excluded(filename):
    if filename.endswith("stateinfo.json"):   return True
    if filename.endswith("_stateinfo.xml"):   return True
    if filename.endswith(".dvm"):             return True
    if filename == "nxsdmetadata.properties": return True
    if filename == "oic_project.properties":  return True
    if filename == "project.yaml":            return True
    if filename.endswith(".zip"):             return True
    return False

def is_deferred(filename):
    if filename.endswith(".wsdl"):  return True
    if filename.endswith(".jca"):   return True
    if filename.endswith(".xsd"):   return True
    return False
```

## OIC Resource File Type Reference

# OIC Resource File Type Reference
**Version:** 2.0
**Purpose:** Ground truth context document for oic-lens development.
Describes every artifact type found across all 11 IAR/CAR pairs.
Paste this at the start of new windows as design context.

---

## Project Tree Structure

Every CAR/IAR file extracts to this top-level structure:

```
project/
├── project.yaml               ← project metadata, revision history, asset inventory
├── oic_project.properties     ← internal hash, no semantic value
├── rpa.zip                    ← binary RPA artifact
├── connections/               ← one XML file per external connection
├── lookups/                   ← DVM lookup tables (key-value stores)
├── labels/                    ← version label metadata
├── integrations/              ← one dir per integration version
│   └── {CODE}_{VERSION}/
│       ├── info.json
│       └── resources/
│           ├── application_{ID}/   ← adapter connection resources
│           └── processor_{ID}/     ← flow step resources
└── ai_agents/                 ← agent definitions (if present)
    ├── agents/
    ├── tools/
    ├── patterns/
    └── promptTemplates/
```

**Two workspace variants observed:**
- FACTORYDOCK pairs: `project/` is at root of extract
- INT303 pair (55-56): `project/` is under `icspackage/`

---

## Path Structure Inside `resources/`

Two depth variants exist under `resources/processor_{ID}/`:

```
Shallow (most file types):
  resources/processor_{ID}/resourcegroup_{RG}/{file}

Deep (router branch conditions only):
  resources/processor_{ID}/output_{OUT}/resourcegroup_{RG}/{file}
```

**Normalisation rule for cross-version comparison:**
- Strip `resourcegroup_{ID}` segment — it changes between versions even when
  content is identical (UI designer assigns new IDs on every save)
- Preserve `output_{ID}` segment — it is stable across versions and identifies
  which router branch the file belongs to
- Normalised key examples:
  - Shallow: `expr.properties`
  - Deep: `output_966/expr.properties`
  - Shallow XSL: `req_abc123.xsl`

---

## Design Principle: LLM as Architect

The LLM receives a **structured inventory** (the map) upfront and **requests
file contents on demand**. The tool does not pre-filter what the LLM sees
beyond excluding files with provably zero semantic value.

Two categories:

| Category | Meaning |
|---|---|
| **LLM-readable** | LLM can request and reason about these |
| **Excluded** | Provably zero semantic value — never sent to LLM |

---

## Project-Level Artifacts

### `project.yaml` — Project Manifest
**Location:** `project/project.yaml`
**Category: EXCLUDED**
**Content:** Project code, name, revision numbers, timestamps, full asset
inventory (integrations, connections, lookups, labels, agents) with last-updated
dates and author emails.
**Why excluded:** Changes between versions are always timestamp and revision
counter updates. The asset inventory is useful context but is derivable from
the extracted workspace itself. Author emails and tenant OCIDs are noise.

---

### `connections/{CODE}.xml` — External Connection Definition
**Location:** `project/connections/`
**Category: LLM-READABLE**
**Content:** XML with connection code, display name, adapter type
(`applicationTypeRef`), security policy, connection properties (service name,
host, port), and credential key references (hashed — not actual credentials).
**Example fields:**
```xml
<instanceCode>ALTERA_ATP</instanceCode>
<displayName>Altera ATP</displayName>
<applicationTypeRef>atpdatabase</applicationTypeRef>
<securityPolicy>JDBC_OVER_SSL</securityPolicy>
<connectionProperty><n>ServiceName</n><value>atpuat_high</value></connectionProperty>
```
**Role:** Tells the LLM what external systems the integration connects to,
what adapter type is used, and what security policy is in place.
**Relevance for architect review:** Security policy changes, new connections
added, or connection reconfiguration are all meaningful findings.
**Note:** Credential values are hashed keys, not plaintext secrets. Safe to
pass to LLM.
**Observed in 32-33:** Connections did NOT change between v32 and v33.
Could change in other pairs.

---

### `lookups/{NAME}.dvm` — Domain Value Map (Lookup Table)
**Location:** `project/lookups/`
**Category: EXCLUDED (out of scope)**
**Content:** XML key-value lookup table. In observed pairs contains email
addresses mapped to role keys (CC, fromEmail, instance label).
**Why excluded:** Contains PII (email addresses). Out of scope for diff/review
per project decision.

---

### `labels/{CODE}.json` — Version Label
**Location:** `project/labels/`
**Category: EXCLUDED**
**Content:** JSON with label name, code, revision, and list of integration +
agent versions pinned to this label.
**Why excluded:** Bookkeeping only — tracks which version is tagged as TEST,
PROD, etc. Not flow logic.

---

### `oic_project.properties` — Internal Hash
**Location:** `project/oic_project.properties`
**Category: EXCLUDED**
**Content:** `mod=el9IDyT/...` — internal integrity hash.
**Why excluded:** Zero semantic value.

---

### `rpa.zip` — RPA Binary
**Location:** `project/rpa.zip`
**Category: EXCLUDED**
**Content:** Binary ZIP. Not readable.

---

## Integration Processor Resources

All files under `project/integrations/{CODE}/resources/processor_{ID}/`.

### `expr.properties` — Expression / Variable Definition
**Matches:** any filename ending with `expr.properties`
**Includes:** plain `expr.properties` AND compound names like
`SUBJECT_PARAM_1expr.properties`, `CODEexpr.properties`,
`StatusMessageexpr.properties`, `instanceIdexpr.properties`, etc.
**Category: LLM-READABLE**
**Content structure:**
```
TextExpression : Status = 'Awaiting Shipping' OR varCount >= '11'
XpathExpression : $getSOLineStatus/.../Status = 'Awaiting Shipping' or $varCount >= '11'
NamespaceList : ns30=http://... ns29=http://...
NumberOfWarnings : 0
NumberOfErrors : 0
ExpressionName :
VariableName : varCount
VariableType : string
```
**Key fields:**
- `TextExpression` — human-readable expression as typed in the OIC designer
- `XpathExpression` — the actual XPath executed at runtime
- `VariableName` — variable being assigned (for assignment processors)
- `ExpressionName` — branch label (for router output branches)
**Role:** Primary logic file. Contains routing conditions, variable assignments,
wait durations, and notification parameter values.
**Compound name pattern:** The filename prefix is the parameter name.
`SUBJECT_PARAM_1expr.properties` = email subject expression.
`FROM_PARAM_1expr.properties` = sender address expression.
**Normalisation:** Strip trailing whitespace per line before comparing.

---

### `req_{hash}.xsl` — XSLT Data Mapping
**Matches:** filename matching pattern `req_*.xsl`
**Category: LLM-READABLE**
**Content:** Full XSLT 2.0 stylesheet generated by OIC mapper. Contains
field-level mappings, XPath expressions, DVM lookups, concat operations,
conditional logic, and namespace declarations.
**Role:** Complete data transformation logic for transformer (mapper) steps.
Defines what data is passed to downstream systems and how it is shaped.
**CRITICAL NOTE — Hash filename change:**
The filename is a content hash. If XSL content changes, the hash changes,
so the filename changes. A modified XSL appears as "file removed + file added"
not "file modified". Diff logic must detect this pattern and treat it as a
single modification. Rule: if source has one `req_*.xsl` and target has one
`req_*.xsl` for the same processor, treat as modified regardless of hash difference.

---

### `notification_*.data` — Email Notification Content
**Matches:** filenames starting with `notification_` and ending with `.data`
**Includes:** `notification_body.data`, `notification_subject.data`,
`notification_to.data`, `notification_from.data`, `notification_cc.data`
**Category: LLM-READABLE**
**Content:**
- `notification_body.data` — full HTML email template with `{variable}` placeholders
- `notification_subject.data` — subject line, typically `{SUBJECT_PARAM_1}`
- `notification_to.data` — To address, typically `{TO_PARAM_1}`
- `notification_from.data` — From address, typically `{FROM_PARAM_1}`
- `notification_cc.data` — CC address, typically `{CC_PARAM_1}`
**Role:** Defines email content for notification steps. Changes here affect
what recipients receive.

---

### `stitch.json` — Variable Assignment (Stitch Processor)
**Matches:** exact filename `stitch.json`
**Category: LLM-READABLE**
**Content:** JSON array of assignment operations:
```json
{
  "stitches": [
    {
      "@type": "Assign",
      "from": { "expression": "$createSORest/.../HeaderId" },
      "to":   { "path": "$soHeaderId" }
    }
  ]
}
```
**Role:** The stitch processor's equivalent of `expr.properties` — defines
variable assignments at runtime.
**Normalisation:** Sort JSON keys before comparing to suppress key-order
churn between versions that has no semantic meaning.

---

### `*.wsdl` (under processor_* / application_*) — Adapter WSDL Contract
**Matches:** `*.wsdl` files under processor or application resource dirs
**Category: LLM-READABLE — deferred to security review milestone**
**Content:** Generated WSDL describing adapter port type, operations, and
message types.
**Role:** Defines the interface contract for an adapter connection. Changes
here indicate adapter version upgrades or operation changes.
**Current scope:** Excluded from M2 diff output. Flagged `deferred: true`
in inventory. Will be included when security review milestone is in scope.

---

### `*.jca` (under processor_* / application_*) — JCA Adapter Configuration
**Matches:** `*.jca` files under processor or application resource dirs
**Category: LLM-READABLE — deferred to security review milestone**
**Content:** XML adapter config — connection factory, activation spec, file
adapter properties (schema element, read mode, chunk size, etc.).
**Role:** Technical adapter configuration. Changes here indicate adapter
reconfiguration.
**Current scope:** Excluded from M2 diff output. Flagged `deferred: true`.

---

### `*.xsd` (under processor_* / application_*) — XML Schema
**Matches:** `ICSFault.xsd`, `ICSIntegrationMetadata.xsd`, `ICSSchedule_1.xsd`,
adapter-specific XSD files
**Category: LLM-READABLE — deferred to security review milestone**
**Current scope:** Excluded from M2 diff output. Flagged `deferred: true`.

---

### `*stateinfo.json` — UI Designer State (JSON)
**Matches:** any filename ending with `stateinfo.json`
**Includes:** plain `stateinfo.json` AND compound names like
`CODEstateinfo.json`, `SUBJECT_PARAM_1stateinfo.json`, etc.
**Category: EXCLUDED**
**Content:** JSON with variable references and absolute `/tmp/WC/itg_{uuid}/`
paths that change with every designer session.
**Why excluded:** Always differs between versions regardless of whether
anything meaningful changed. Zero runtime impact.

---

### `req_{hash}_stateinfo.xml` — XSL Mapper UI State (XML)
**Matches:** filename matching `req_*_stateinfo.xml`
**Category: EXCLUDED**
**Content:** XML with absolute `file:/tmp/WC/itg_{uuid}/` designer session paths.
**Why excluded:** Designer UI state only. Always differs. Zero runtime impact.

---

### `nxsdmetadata.properties` — Native Schema Metadata
**Matches:** exact filename `nxsdmetadata.properties`
**Category: EXCLUDED**
**Content:** `{}` (empty in all observed samples).

---

## AI Agent Resources

All files under `project/ai_agents/`.
Present in FACTORYDOCK pairs (32-33 through 53-54). Not present in INT303 (55-56).

### `*.jq` — JQ Expression (Agent Processor)
**Matches:** any filename ending with `.jq`
**Includes:** `agentGuideline.jq`, `agentRole.jq`, `agenticTrigger.jq`,
`patternRoles.jq`, `payload.jq`, `prompt.jq`, `prompt_id.jq`, `userPrompt.jq`
**Category: LLM-READABLE**
**Content:**
```json
{
  "jqExpression": "$start.body.payload",
  "variableName": "payload"
}
```
**Role:** Agent equivalent of `expr.properties`. The `jqExpression` field
is the runtime logic. Changes here affect what data the agent processes.

---

### `guideline.txt` — Agent Guideline
**Matches:** exact filename `guideline.txt`
**Category: LLM-READABLE**
**Content:** Plain text operating instruction for the AI agent at runtime.
**Role:** Directly affects agent behaviour.

---

### `role.txt` — Agent Role Definition
**Matches:** exact filename `role.txt`
**Category: LLM-READABLE**
**Content:** Plain text role/persona definition for the AI agent.

---

### `agents/{CODE}/info.json` — Agent Metadata
**Category: LLM-READABLE**
**Content:** Agent code, name, description, version, and dependencies
(tools, patterns, promptTemplates it uses).

---

### `tools/{CODE}/tool.properties` — Agent Tool Definition
**Category: LLM-READABLE**
**Content:** Links an integration as a callable tool for the agent.
Fields: tool code, name, description, toolType, version.

---

### `tools/{CODE}/content.json` — Agent Tool Content
**Category: LLM-READABLE**
**Content:** Tool input/output schema and invocation details.

---

### `promptTemplates/{CODE}/content.json` — Prompt Template
**Category: LLM-READABLE**
**Content:** The actual prompt text given to the LLM inside the agent.
Changes here directly affect agent output quality.

---

### Agent `*stateinfo.json`, `*.wsdl`, `*.jca`, `*.xsd` (under ai_agents/)
Same rules as their integration counterparts above.

---

## Exclusion Rules for `file_diff.py`

```python
def is_excluded(filename):
    """Files never included in diff output — provably zero semantic value."""
    if filename.endswith("stateinfo.json"):   return True  # UI state
    if filename.endswith("_stateinfo.xml"):   return True  # XSL mapper UI state
    if filename.endswith(".dvm"):             return True  # lookups — out of scope
    if filename == "nxsdmetadata.properties": return True  # empty
    if filename == "oic_project.properties":  return True  # internal hash
    if filename == "project.yaml":            return True  # timestamps
    if filename.endswith(".zip"):             return True  # binary
    return False

def is_deferred(filename):
    """LLM-readable but not included until security review milestone."""
    if filename.endswith(".wsdl"):  return True
    if filename.endswith(".jca"):   return True
    if filename.endswith(".xsd"):   return True
    return False
```

Everything not excluded and not deferred goes into the diff engine as-is.
The LLM decides what is significant.

---

## XSL Hash Filename Handling

XSL files use content-hash filenames: `req_{md5hash}.xsl`

A content change causes a filename change. Naive diff sees: removed + added.
Correct handling: if source has exactly one `req_*.xsl` and target has exactly
one `req_*.xsl` for the same processor, treat as a single modified file.
Report old filename, new filename, old content, new content.

---

## Observed Pairs

| Pair | Integration Code | Type | Agent present |
|------|-----------------|------|---------------|
| 32-33 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 34-35 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 36-37 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 39-40 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 41-42 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 45-46 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 47-48 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 49-50 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 51-52 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 53-54 | ALTERA_CREATE_SO_INTEGRAT | REST/SOAP Sales Order | Yes |
| 55-56 | INT303_INVENTOR_EI_RECONCIL | File-based EI Reconciliation | No |


## Handoff Block

### Completed milestones
- M0 ✅ — Project Bootstrap
- M1 ✅ — Structural Delta — New + Removed Steps

### Current milestone
**M1 — Structural Delta — New + Removed Steps — DONE**

### Open questions
_Update this section manually before saving._

### Exact next action
_Update this section manually before saving._
