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
