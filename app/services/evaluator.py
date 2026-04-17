"""Post-interview evaluator — transcript formatting and report generation."""

_DRIVER_PHASES = {"thinking", "action", "people", "mastery"}

_DRIVER_LABELS = {
    "thinking": "THINKING (Power of Thinking — Strategic)",
    "action": "ACTION (Power of Action — Leadership)",
    "people": "PEOPLE (Power of People — Collaboration)",
    "mastery": "MASTERY (Power of Mastery — Technical)",
}


def _format_transcript(history: list[dict]) -> str:
    """Format interview history into a structured transcript.

    Includes driver labels, competency being assessed (from the opener's
    history entry), Alex's questions, and candidate answers.
    """
    parts: list[str] = []
    current_phase = None
    phase_started: set[str] = set()

    for msg in history:
        role = msg.get("role")
        phase = msg.get("phase")

        if role == "assistant" and phase in _DRIVER_PHASES:
            if phase not in phase_started:
                phase_started.add(phase)
                label = _DRIVER_LABELS.get(phase, phase.upper())
                comp = msg.get("competency")
                if comp:
                    parts.append(f"\n[{label} — Competency: {comp}]")
                else:
                    parts.append(f"\n[{label}]")
            parts.append(f'Alex: "{msg["content"]}"')
            current_phase = phase

        elif role == "user" and current_phase in _DRIVER_PHASES:
            parts.append(f'Candidate: "{msg["content"]}"')

    return "\n".join(parts)
