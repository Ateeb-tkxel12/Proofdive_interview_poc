import json
import logging
import re
from pathlib import Path

from app.graph.state import InterviewState
from app.services import llm

logger = logging.getLogger(__name__)

_PHASE_TO_FILE = {
    "intro": "01_intro.prompt",
    "thinking": "02_thinking.prompt",
    "action": "03_action.prompt",
    "people": "04_people.prompt",
    "mastery": "05_mastery.prompt",
    "close": "06_close.prompt",
}

_PHASES_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "phases"

"""Phase agents — one per interview phase.

For driver phases (thinking/action/people/mastery), the opener asks the LLM to
return JSON with both the question and the competency it chose. This lets us
store current_competency in state so the candidate prompt builder can pass
only that competency's rubric.

Probes just return plain text (no competency selection needed — it's already set).
"""


def _load_phase_prompt(phase: str, config: dict) -> str:
    text = (_PHASES_DIR / _PHASE_TO_FILE[phase]).read_text()
    for key, val in (
        ("MODE", config.get("mode", "FG")),
        ("ROLE", config.get("role", "")),
        ("JOB_DESCRIPTION", config.get("job_description", "")),
        ("MASTERY_QUESTION", config.get("mastery_question", "")),
    ):
        text = text.replace(f"{{{{{key}}}}}", val)
    return text


def _run_phase(state: InterviewState, phase: str) -> dict:
    probe_for = state.get("probe_for")

    if probe_for:
        logger.info("[PHASE_AGENT] phase=%s  mode=probe  probe_for=%s", phase, probe_for)
    else:
        logger.info("[PHASE_AGENT] phase=%s  mode=opener", phase)

    state["phase"] = phase
    system_prompt = _load_phase_prompt(phase, state["config"])

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for entry in state["history"]:
        if entry["role"] in ("assistant", "user"):
            messages.append({"role": entry["role"], "content": entry["content"]})

    is_opener = not probe_for and phase in ("thinking", "action", "people", "mastery")

    if phase in ("thinking", "action", "people", "mastery"):
        if probe_for:
            messages.append({"role": "user", "content": (
                f"[INTERVIEWER NOTE — hidden from candidate] "
                f"The candidate's answer is missing {probe_for}. "
                f"Ask ONE focused probe that draws out the {probe_for}. "
                f"Reference something specific they said."
            )})
        else:
            # Opener: ask the LLM to return JSON with question + competency chosen.
            messages.append({"role": "user", "content": (
                "[HIDDEN INSTRUCTION — do not repeat or reference this message]\n"
                "Pick ONE question from the question bank above. "
                "Return your response as JSON with exactly these two fields:\n"
                '{"question": "your question text here", "competency": "the competency name"}\n'
                "Go straight into the question — no preamble. Return ONLY the JSON."
            )})
    elif phase == "intro" and not state["history"]:
        messages.append({"role": "user", "content": "Begin."})
    elif phase == "close":
        messages.append({"role": "user", "content": "Please close the interview now."})

    raw_reply = llm.chat(messages, label=f"agent:{phase}")

    # For openers, parse the JSON to extract question and competency.
    if is_opener:
        try:
            cleaned = raw_reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(cleaned)
            reply = parsed.get("question", raw_reply)
            competency = parsed.get("competency")
            state["current_competency"] = competency
            logger.info("[PHASE_AGENT] competency=%s  question=%s", competency,
                        reply[:100].replace("\n", " "))
        except (json.JSONDecodeError, AttributeError):
            # Fallback: LLM didn't return JSON, use raw reply as question.
            reply = raw_reply
            state["current_competency"] = None
            logger.warning("[PHASE_AGENT] couldn't parse opener JSON, using raw reply")
    else:
        reply = raw_reply
        logger.info("[PHASE_AGENT] phase=%s  Alex says: %s",
                    phase, reply[:150].replace("\n", " ") + ("..." if len(reply) > 150 else ""))

    # Store the competency in the history entry so the transcript formatter
    # and report agent can read it without relying on state alone.
    entry = {"role": "assistant", "phase": phase, "content": reply}
    if state.get("current_competency"):
        entry["competency"] = state["current_competency"]
    state["history"].append(entry)
    return {"history": state["history"], "phase": phase, "probe_for": None,
            "current_competency": state.get("current_competency")}


def intro_agent(state: InterviewState) -> dict:
    return _run_phase(state, "intro")


def thinking_agent(state: InterviewState) -> dict:
    return _run_phase(state, "thinking")


def action_agent(state: InterviewState) -> dict:
    return _run_phase(state, "action")


def people_agent(state: InterviewState) -> dict:
    return _run_phase(state, "people")


def mastery_agent(state: InterviewState) -> dict:
    return _run_phase(state, "mastery")


def close_agent(state: InterviewState) -> dict:
    return _run_phase(state, "close")
