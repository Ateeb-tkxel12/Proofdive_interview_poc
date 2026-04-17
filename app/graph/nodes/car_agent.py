import json
import logging
import re
from pathlib import Path

from app.graph.state import InterviewState
from app.services import llm

logger = logging.getLogger(__name__)

_DEFAULT_CAR = {"context": False, "action": False, "result": False}
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "car" / "car_evaluation.prompt"

"""CAR Agent — judges the latest candidate answer for Context / Action / Result.

The verdict goes into history as its own entry shaped like:

    {"role": "car_judge", "phase": "<driver>",
     "car": {"context": bool, "action": bool, "result": bool}}

That's how the orchestrator "sees" CAR signal on its next hop.

Reads:   state["history"], state["phase"]
Writes:  appends a car_judge entry to state["history"]
Routed from: orchestrator (when the last user message in a driver phase has no
             car_judge entry after it yet)
Routes to:   orchestrator (loops back within the same turn)
"""

def _latest_user_answer(history: list[dict]) -> str:
    """Find the most recent candidate answer. Empty string if none."""
    for entry in reversed(history):
        if entry.get("role") == "user":
            return entry.get("content", "")
    return ""


def car_agent(state: InterviewState) -> dict:
    answer = _latest_user_answer(state["history"])
    phase = state.get("phase", "thinking")
    logger.info("[CAR_AGENT] phase=%s  answer_len=%d", phase, len(answer))

    # No user answer to judge yet — append a safe-default verdict so the
    # orchestrator doesn't loop calling us.
    if not answer:
        state["history"].append({"role": "car_judge", "phase": phase, "car": dict(_DEFAULT_CAR)})
        return {"history": state["history"]}

    # Load the CAR evaluation prompt and inject the candidate's answer.
    prompt = _PROMPT_PATH.read_text().replace("{{ANSWER}}", answer)

    messages = [
        {"role": "system", "content": prompt},
    ]

    # Parse best-effort. Any failure → default (false, false, false).
    car = dict(_DEFAULT_CAR)
    try:
        raw = llm.chat(messages, label=f"car:{phase}")
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            car = {k: bool(parsed.get(k, False)) for k in ("context", "action", "result")}
    except Exception as e:
        logger.warning("[CAR_AGENT] parse failed: %s", e)

    logger.info("[CAR_AGENT] verdict  C=%s  A=%s  R=%s", car["context"], car["action"], car["result"])
    state["history"].append({"role": "car_judge", "phase": phase, "car": car})
    return {"history": state["history"]}
