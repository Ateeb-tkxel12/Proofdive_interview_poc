from typing import TypedDict

"""Interview state — deliberately minimal.

Everything we need to drive the interview lives in `history`. Probe counts,
CAR progress, and turn context are all *derived* from history when the
orchestrator needs them — we don't keep parallel tracking fields.

History entries come in three shapes:

    {"role": "assistant", "phase": "thinking", "content": "..."}   # Alex asking
    {"role": "user",      "phase": "thinking", "content": "..."}   # Candidate answering
    {"role": "car_judge", "phase": "thinking",
     "car": {"context": True, "action": False, "result": False}}   # CAR verdict
"""

class InterviewState(TypedDict, total=False):
    config: dict                 # mode, role, job_description, mastery_question
    phase: str                   # intro | thinking | action | people | mastery | close | done
    history: list[dict]          # see module docstring for entry shapes
    next_action: str | None      # orchestrator's latest pick (debug / UI)
    probe_for: str | None        # CAR element to probe for (e.g. "ACTION"), set by orchestrator, None = opener
    current_competency: str | None  # which competency the current question targets (e.g. "Analytical Thinking")
    final_report: dict | None    # populated by report_agent at the end


def new_state(config: dict) -> InterviewState:
    """Fresh state at the start of an interview. Orchestrator takes it from here."""
    return InterviewState(
        config=config,
        phase="intro",
        history=[],
        next_action=None,
        final_report=None,
    )
