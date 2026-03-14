# iar-lens — Next Session Context & Goals

## What This Project Is
A Python + LangGraph + Gemini tool that compares two versions of an Oracle Integration Cloud (OIC) .iar/.car archive file and produces a structured change review report in Markdown. Used by architects to approve/reject OIC integration deployments.

## GitHub
github.com/bhagavansprasad/iar-lens

## Pipeline (3 stages)
```
Stage 1 — test_comparison.py
  iar_compare.py → extracts IARs, computes delta, calls LLM flow understander
  Outputs: <label>_delta.json + <label>_flow_context.json

Stage 2 — test_agent.py
  iar_agent.py (LangGraph) → investigates changed processors, synthesizes report
  Outputs: <label>_report.json

Stage 3 — test_report.py
  report_generator.py → renders Markdown report with Mermaid diagrams
  Outputs: <label>_change_report.md
```

## Test Pairs
- 32-33: ALTERA_CREATE_SO_INTEGRAT v01.00.0032→0033 (8 new steps, 0 removed)
- 49-50: ALTERA_CREATE_SO_INTEGRAT v01.00.0049→0050 (0 changes, refactor)
- 55-56: INT303_INVENTOR_EI_RECONCIL v03.00.0001→0011 (15 new, 8 removed)

## Current Git State
- master: has Phase 5 Commits 1+2+3 merged
- feature/phase5-commit4-flow-diagram: LOCAL ONLY, not pushed yet
  - Only file changed: src/report_generator.py

---

## Immediate Next Steps (Session Goals)

### GOAL 1 — Validate Commit 4 (report_generator.py changes)
Run and share output for all 3 pairs:
```bash
python test/test_report.py 55-56
python test/test_report.py 32-33
python test/test_report.py 49-50
```
Check for:
- Section numbers sequential (no gaps like 8→10)
- Section 4 (Flow Diagram) skipped for 49-50 (no changes)
- Balanced node rows (8-12 nodes per row, last row similar size to others)
- Green=new, Red=removed nodes in correct positions
- No raw Mermaid text leaking outside code blocks

### GOAL 2 — Commit 4
```bash
git checkout -b feature/phase5-commit4-flow-diagram
git add src/report_generator.py
git commit -m "feat: Phase 5 Commit 4 — full flow diagram + narrative sections + dynamic numbering

- _build_full_flow_diagram(): Before/After Mermaid LR diagrams
  - Balanced rows 8-12 nodes per row (no uneven last row)
  - Separate Mermaid block per row for reliable horizontal rendering
  - Green=new, Red=removed, Grey=unchanged/shifted
  - Skipped for no-change integrations (shows info note instead)
- _build_what_it_does(): Section from flow_context.integration_purpose
- _build_what_changed(): Section from flow_context narrative fields
- Dynamic section renumbering: §N§ placeholders replaced sequentially
  so numbers stay correct when sections are hidden
- Empty sections hidden: New Steps, Removed Steps when count=0
- Approval Conditions: shows message when no conditions
- Node label truncation: 14 chars for consistent node sizing
- MAX_NODES raised to 200
- Footer: Gemini -> LLM"
git push -u origin feature/phase5-commit4-flow-diagram
```
Then PR → merge to master.

### GOAL 3 — Commit 5 (mark complete, already done)
Sections 2+3 were added in Commit 3. No further work needed.
Just note in PR/commit log that Commit 5 scope was merged into Commit 3.

### GOAL 4 — Commit 6: End-to-end validation
Uncomment all 3 pairs in run_batch.py and run the full pipeline:
```bash
# Edit src/run_batch.py to uncomment all 3 pairs
python src/run_batch.py
```
Verify all 3 pairs produce correct output files end-to-end.

### GOAL 5 — Migrate google.generativeai → google.genai (housekeeping)
Check for any remaining old import:
```bash
agrep "google.generativeai" src/
```
Migrate any found files to use:
```python
import google.genai as genai
client = genai.Client()
response = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
```

---

## Key Technical Decisions Made (do not reverse)
- All output files labelled: <label>_delta.json, <label>_flow_context.json, <label>_report.json
- flow_context computed in Stage 1 (iar_compare.py), not in test scripts
- systems_involved computed in Python (not LLM) to avoid truncation
- google.genai Client() with no args (picks up GOOGLE_API_KEY from env)
- Mermaid diagrams: separate flowchart LR block per row of 8-12 nodes
- Section numbers dynamic (not hardcoded) to handle hidden sections

## File Structure
```
src/
  iar_compare.py       — Stage 1 orchestrator
  flow_understander.py — LLM flow context (called by Stage 1)
  flow_compare.py      — Pure Python delta computation
  extractor.py         — IAR/CAR zip extraction
  iar_agent.py         — Stage 2 LangGraph agent
  iar_agent_prompts.py — LLM prompts with flow_context injection
  iar_agent_state.py   — LangGraph state schema
  report_generator.py  — Stage 3 Markdown renderer
  run_batch.py         — Full pipeline runner
test/
  test_comparison.py   — Stage 1 standalone test
  test_agent.py        — Stage 2 standalone test
  test_report.py       — Stage 3 standalone test
flow-dump/             — Input .iar/.car files
output/                — All labelled output files
workspace/             — Temp extraction dirs (KEEP_WORKSPACE=True)
config.py              — GEMINI_MODEL, LABEL, OUTPUT_DIR etc
```
