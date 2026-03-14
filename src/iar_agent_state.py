# ---------------------------------------------------------------------------
# iar-lens | src/iar_agent_state.py
# State schema for the IAR Review LangGraph Agent
# ---------------------------------------------------------------------------

from typing import TypedDict, Optional, List, Dict, Any


class IARReviewAgentState(TypedDict):
    # -----------------------------------------------------------------------
    # Input — provided at invocation time
    # -----------------------------------------------------------------------
    delta_path    : str          # path to delta.json from Phase 1
    version_from  : str          # e.g. "03.00.0001"
    version_to    : str          # e.g. "03.00.0011"
    integration   : str          # e.g. "INT303_INVENTOR_EI_RECONCIL"

    # -----------------------------------------------------------------------
    # Working state — built and consumed internally by nodes
    # -----------------------------------------------------------------------
    delta              : Optional[Dict[str, Any]]   # loaded delta.json content
    flow_context       : Optional[Dict[str, Any]]   # loaded <label>_flow_context.json (Phase 1b)
    reading_list       : Optional[List[Dict]]       # processors to investigate
    files_read         : Optional[List[Dict]]       # all files read so far
    findings           : Optional[List[Dict]]       # per-processor findings

    # -----------------------------------------------------------------------
    # Output — final report produced by SYNTHESIZE node
    # -----------------------------------------------------------------------
    final_report  : Optional[Dict[str, Any]]        # structured delta report + summary
