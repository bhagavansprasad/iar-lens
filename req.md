# iar-lens — Test Data Preparation Guide
### Instructions for Integration Engineer

---

## Background

We are building an automated tool called **iar-lens** that compares two versions of an OIC integration and generates a change report.

**Your job is to prepare test data** — we will use your data to validate the tool's output against what you expect to see.

---

## What You Need to Deliver

For each test set, provide **3 things**:

```
Set X/
  ├── integration_vX.iar.zip       ← source version
  ├── integration_vY.iar.zip       ← target version
  └── expected_output.md           ← your manually written expected report
```

Prepare **at least 10 sets** following the guidelines below.

---

## How to Write expected_output.md

Open both IAR versions in OIC and manually document:

1. **List of new steps** — name, type, position, what it does in one sentence
2. **List of removed steps** — name, type, position, what it did in one sentence
3. **Overall risk** — Low / Medium / High and why
4. **Summary** — 3–5 sentences describing what changed and why

### Example expected_output.md

```markdown
## Integration: MY_INTEGRATION
## Version: v1.0 → v2.0

### New Steps
1. ForEachDHLFiles (for, position 31) — loops over DHL files retrieved from FTP
2. ReadDhlInvData (stageFile, position 35) — reads DHL CSV inventory file

### Removed Steps
1. CallOracleInventorySync (transformer, position 30) — called Oracle inventory sync service

### Overall Risk: HIGH
Reason: Oracle Inventory Sync call removed — downstream systems may be affected

### Summary
Version 2.0 replaces the Oracle Inventory Sync call with a new DHL file processing
loop. The new flow lists files from FTP, reads each CSV, and inserts into ATP database.
The removal of the Oracle sync is a high risk change that needs verification.
```

---

## Test Set Guidelines

Prepare sets with variety — the more variety, the better the validation:

| Set | What to Pick |
|---|---|
| Set 1 | Integration with **very few steps** (5–10 nodes), small change |
| Set 2 | Integration with **many steps** (40+ nodes), multiple changes |
| Set 3 | Integration with a **ForEach loop** added or removed |
| Set 4 | Integration where steps have **detailed expressions and DVM lookups** |
| Set 5 | Integration where steps have **minimal configuration** (sparse metadata) |
| Set 6 | Integration where **notification steps** (email) were added or removed |
| Set 7 | Integration where an **adapter/connection** was replaced |
| Set 8 | Integration where **error handling** (CatchAll or Throw) changed |
| Set 9 | Integration with a **major block replacement** (5+ steps replaced by different 5+ steps) |
| Set 10 | Integration with **no changes** — same version used as both source and target |

---

## Delivery Format

Create a folder named `iar-lens-test-data` with this structure:

```
iar-lens-test-data/
  ├── set01/
  │     ├── integration_v1.iar.zip
  │     ├── integration_v2.iar.zip
  │     └── expected_output.md
  ├── set02/
  │     ├── integration_v1.iar.zip
  │     ├── integration_v2.iar.zip
  │     └── expected_output.md
  ...
  └── set10/
        ├── integration_v1.iar.zip
        ├── integration_v2.iar.zip
        └── expected_output.md
```

---

## Notes

> The expected output in each set is a starting point prepared by the tools engineer. The integration engineer knows the integration better — feel free to correct or improve it. Your refined output takes priority over the baseline.


- Use **real integrations** from any OIC environment you have access to
- The more variety across sets the better — avoid using the same integration multiple times
- The `expected_output.md` does not need to be perfect — write what you honestly expect to see
- If you are unsure about risk level, make your best judgement and note your reasoning

---

*Prepared for iar-lens validation — share completed test data with the architect*