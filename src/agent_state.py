# ---------------------------------------------------------------------------
# oic-lens | src/agent_state.py
# M4 — Agent Investigation
# State schema for the LangGraph Investigator Agent
# ---------------------------------------------------------------------------

from typing import TypedDict, Optional, List, Dict, Any
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    # -----------------------------------------------------------------------
    # Input — provided at invocation time
    # -----------------------------------------------------------------------
    delta_path   : str               # path to {label}_delta.json
    version_from : str               # e.g. "01.00.0032"
    version_to   : str               # e.g. "01.00.0033"
    integration  : str               # e.g. "ALTERA_CREATE_SO_INTEGRAT"

    # -----------------------------------------------------------------------
    # Working state — built and consumed internally by nodes
    # -----------------------------------------------------------------------
    delta              : Optional[Dict[str, Any]]  # loaded delta.json content
    flow_context       : Optional[Dict[str, Any]]  # loaded {label}_flow_context.json
    inventory          : Optional[Dict[str, Any]]  # structured map built by BUILD_INVENTORY
    modified_steps     : Optional[List[Dict]]      # first-class — from delta["modified_steps"]
    files_read         : Optional[List[str]]       # log of every file read (for report metadata)
    findings           : Optional[List[Dict]]      # per-processor findings from INVESTIGATE

    # -----------------------------------------------------------------------
    # Output — final report produced by SYNTHESIZE node
    # -----------------------------------------------------------------------
    final_report : Optional[Dict[str, Any]]        # structured report → {label}_report.json
