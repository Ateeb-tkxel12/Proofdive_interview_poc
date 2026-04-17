"""Supervisor graph — orchestrator-on-top architecture.

Flow (read this once and the rest of the module follows):

    Every turn starts at the orchestrator. It picks ONE of these actions:

        intro | thinking | action | people | mastery | close | car_agent | report | end

    car_agent is the ONLY node that loops back to the orchestrator in the same
    turn — it appends a car_judge verdict, and the orchestrator immediately
    re-reads history to decide whether to probe or advance. Every other node
    ends the turn so the UI can wait for the next candidate input.

    ┌───────────────────────────────────────────────────────────────┐
    │  START → orchestrator                                         │
    │             ├── "intro"      → intro_agent     → END          │
    │             ├── "thinking"   → thinking_agent  → END          │
    │             ├── "action"     → action_agent    → END          │
    │             ├── "people"     → people_agent    → END          │
    │             ├── "mastery"    → mastery_agent   → END          │
    │             ├── "close"      → close_agent     → END          │
    │             ├── "car_agent"  → car_agent ──┐                  │
    │             │                              └──► orchestrator  │
    │             ├── "report"     → report_agent   → END           │
    │             └── "end"                          → END          │
    └───────────────────────────────────────────────────────────────┘

One `invoke_turn(state)` call = one traversal from START to the first END.
"""

import logging

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

from app.graph.nodes.car_agent import car_agent
from app.graph.nodes.orchestrator import orchestrator
from app.graph.nodes.phase_agents import (
    action_agent,
    close_agent,
    intro_agent,
    mastery_agent,
    people_agent,
    thinking_agent,
)
from app.graph.nodes.report_agent import report_agent
from app.graph.state import InterviewState

# Maps orchestrator's `next_action` string to the corresponding node name.
# Any value not in this map routes to END.
_ROUTES = {
    "intro": "intro_agent",
    "thinking": "thinking_agent",
    "action": "action_agent",
    "people": "people_agent",
    "mastery": "mastery_agent",
    "close": "close_agent",
    "car_agent": "car_agent",
    "report": "report_agent",
}


def _after_orchestrator(state: InterviewState) -> str:
    """Read orchestrator's decision and pick the matching node. 'end' or anything
    unknown routes to END."""
    action = state.get("next_action")
    target = _ROUTES.get(action, END)
    logger.info("[GRAPH] routing  %s → %s", action, target)
    return target


def build_graph():
    g = StateGraph(InterviewState)

    # Register every node.
    g.add_node("orchestrator", orchestrator)
    g.add_node("intro_agent", intro_agent)
    g.add_node("thinking_agent", thinking_agent)
    g.add_node("action_agent", action_agent)
    g.add_node("people_agent", people_agent)
    g.add_node("mastery_agent", mastery_agent)
    g.add_node("close_agent", close_agent)
    g.add_node("car_agent", car_agent)
    g.add_node("report_agent", report_agent)

    # Every turn enters at the orchestrator.
    g.add_edge(START, "orchestrator")

    # Orchestrator picks the next node based on its decision.
    g.add_conditional_edges("orchestrator", _after_orchestrator, {
        "intro_agent": "intro_agent",
        "thinking_agent": "thinking_agent",
        "action_agent": "action_agent",
        "people_agent": "people_agent",
        "mastery_agent": "mastery_agent",
        "close_agent": "close_agent",
        "car_agent": "car_agent",
        "report_agent": "report_agent",
        END: END,
    })

    # car_agent loops back to orchestrator (same turn) — it just recorded a
    # verdict, orchestrator now reads it and decides probe vs advance.
    g.add_edge("car_agent", "orchestrator")

    # Every other agent ends the turn — the UI waits for next user input.
    for node in ("intro_agent", "thinking_agent", "action_agent",
                 "people_agent", "mastery_agent", "close_agent", "report_agent"):
        g.add_edge(node, END)

    return g.compile()


# Compile once at import time and reuse.
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def invoke_turn(state: InterviewState) -> InterviewState:
    """Run one turn of the interview. Returns the updated state."""
    logger.info("")
    logger.info("[TURN] start  phase=%s  history=%d",
                state.get("phase"), len(state.get("history", [])))

    result = get_graph().invoke(state)

    logger.info("[TURN] end    phase=%s  action=%s  history=%d",
                result.get("phase"), result.get("next_action"), len(result.get("history", [])))
    logger.info("")

    return result
