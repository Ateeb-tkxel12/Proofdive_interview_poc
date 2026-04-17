import json
import logging
from pathlib import Path

from app.graph.state import InterviewState
from app.services import llm

logger = logging.getLogger(__name__)

# Prompt lives alongside the rest of the agent prompts.
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "orchestrator" / "orchestrator_system.prompt"

# Keep the history slice the orchestrator sees small — we only need the recent
# context to decide the next hop, not the full transcript.
_HISTORY_WINDOW = 12

"""Orchestrator — the brain.

Runs at the top of every turn. Reads `phase` + `history`, asks the LLM which
agent to run next, and writes the decision into `state["next_action"]`.

No validator, no deterministic fallback: we trust the LLM. If the JSON is
unparseable, we default to "end" so the graph terminates cleanly rather than
looping. Iterating on the orchestrator prompt is the intended fix when the
LLM misbehaves.

Reads:   state["phase"], state["history"]
Writes:  state["next_action"]
Routed from: START (every turn) and from car_agent (which loops back)
"""

def _merged_car(history: list[dict], phase: str) -> dict:
    """OR-merge all car_judge verdicts for the given phase."""
    merged = {"context": False, "action": False, "result": False}
    for entry in history:
        if entry.get("role") == "car_judge" and entry.get("phase") == phase:
            for k in ("context", "action", "result"):
                if entry.get("car", {}).get(k):
                    merged[k] = True
    return merged


def _probe_count(history: list[dict], phase: str) -> int:
    """Count how many car_judge entries exist for this phase."""
    return sum(1 for e in history if e.get("role") == "car_judge" and e.get("phase") == phase)




def orchestrator(state: InterviewState) -> dict:
    phase = state.get("phase")
    history = state.get("history", [])
    logger.info("[ORCHESTRATOR] phase=%s", phase)
    system_prompt = _PROMPT_PATH.read_text()

    car_progress = _merged_car(history, phase)
    probes = _probe_count(history, phase)

    snapshot = {
        "phase": phase,
        "car_progress": car_progress,
        "probe_count": probes,
        "history": history[-_HISTORY_WINDOW:],
        "report_ready": state.get("final_report") is not None,
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            "Decide the next action. State snapshot:\n"
            f"{json.dumps(snapshot, indent=2)}\n\n"
            "Return ONLY the JSON decision."
        )},
    ]

    # Ask the LLM. On any parse failure we default to "end" so the graph
    # terminates gracefully instead of looping on garbage.
    next_action = "end"
    probe_for = None
    reason = "fallback: unparseable orchestrator output"
    try:
        raw = llm.chat(messages, label="orchestrator")
        # Strip any accidental markdown fences and isolate the JSON body.
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        decision = json.loads(cleaned)
        next_action = decision.get("next_action", "end")
        probe_for = decision.get("probe_for")
        reason = decision.get("reason", "")
    except Exception as e:
        logger.warning("[ORCHESTRATOR] parse failed: %s", e)

    logger.info("[ORCHESTRATOR] decision=%s  probe_for=%s  reason=%s", next_action, probe_for, reason)

    state["history"].append({
        "role": "orchestrator",
        "phase": state.get("phase"),
        "next_action": next_action,
        "probe_for": probe_for,
        "reason": reason,
    })

    return {"next_action": next_action, "probe_for": probe_for, "history": state["history"]}
