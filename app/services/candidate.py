import json
from pathlib import Path

from app.services import llm

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts" / "candidate"
_RUBRIC_PATH = Path(__file__).resolve().parent.parent / "prompts" / "evaluator" / "rubric.json"


def load_prompt(variant: str = "normal") -> str:
    path = _PROMPT_DIR / f"candidate_{variant}.prompt"
    return path.read_text()


def _car_instructions_for_level(avg_level: float) -> str:
    """Return CAR and answer-quality instructions scaled to the average level."""
    if avg_level >= 4.5:
        return """## Answer quality — HIGH (Level 5)
- Always include all three CAR elements with depth and specifics
- Context: specific situation with team size, timeline, stakes, named entities
- Action: clear "I" statements with concrete steps, methods, frameworks used
- Result: quantified outcomes — numbers, percentages, before/after comparisons
- Answers are 5-8 sentences, detailed and structured
- Use specific names, numbers, and timeframes throughout"""

    if avg_level >= 3.5:
        return """## Answer quality — GOOD (Level 4)
- Include all three CAR elements but one may be slightly less detailed
- Context: describes the situation with some specifics
- Action: uses "I" with reasonable detail on what was done
- Result: states an outcome, may have one number or named impact
- Answers are 4-6 sentences, solid but not perfect
- Generally specific but occasionally says "it worked well" instead of quantifying"""

    if avg_level >= 2.5:
        return """## Answer quality — AVERAGE (Level 3)
- Usually includes Context and Action but Result is often vague or missing
- Context: describes situation but may lack specifics (no team size, vague timeline)
- Action: mixes "I" and "we" — sometimes unclear what John personally did vs the team
- Result: often vague — "it went well", "they liked it", "it was successful" — rarely quantifies
- Answers are 3-5 sentences, adequate but leave room for probing
- Sometimes trails off without finishing the thought"""

    if avg_level >= 1.5:
        return """## Answer quality — WEAK (Level 2)
- Usually missing 1-2 CAR elements entirely
- Context: jumps straight into action without explaining the situation, OR gives only a vague one-liner setup
- Action: heavy use of "we" — rarely says what HE specifically did; vague verbs like "helped", "worked on", "was involved"
- Result: almost never states an outcome; if pressed, says "I think it was fine" or "the project finished"
- Answers are 2-3 sentences, short and incomplete
- Sounds uncertain — uses "I guess", "I'm not sure exactly", "something like that"
- When probed, adds a little but still stays vague"""

    return """## Answer quality — POOR (Level 1)
- Missing most CAR elements; answers are unfocused
- Context: either no setup at all, or a rambling description that doesn't clarify the situation
- Action: says "we" exclusively or describes events without any personal agency; "things happened" rather than "I did X"
- Result: never states an outcome; deflects with "I don't really remember the specifics" or changes topic
- Answers are 1-3 sentences, fragmented and directionless
- Sounds confused or disengaged — contradicts self, mixes up details
- When probed, repeats what was already said or gives equally vague answers"""


def build_dynamic_prompt(driver_levels: dict[str, int], current_competency: str | None = None,
                         current_phase: str | None = None) -> str:
    """Build a candidate prompt dynamically from rubric.json based on slider values.

    If current_competency is provided (e.g. "Analytical Thinking"), only that
    competency's rubric is included — so the LLM focuses on exactly the right
    behaviors instead of guessing which competency the question targets.
    """
    rubric = json.loads(_RUBRIC_PATH.read_text())

    # Only include the current phase's driver — no need to show all four.
    # If phase is unknown (e.g. intro), skip the driver section entirely.
    driver_instructions = ""
    if current_phase in ("thinking", "action", "people", "mastery"):
        level = driver_levels.get(current_phase, 3)
        level_str = str(level)
        driver = rubric["drivers"][current_phase]
        label = driver["label"]
        anchors = driver["levels"].get(level_str, driver["levels"]["3"])

        if current_competency and current_competency in anchors:
            # Best case: we know exactly which competency — show only that one.
            anchor_text = anchors[current_competency]
            behaviors = [b.strip() for b in anchor_text.split(";") if b.strip()]
            bullet_list = "\n".join(f"  * {b}" for b in behaviors)
            driver_instructions = (
                f"### Current question: {label} — {current_competency} (Level {level})\n"
                f"Your answer MUST demonstrate ALL of these behaviors:\n{bullet_list}"
            )
        else:
            # Fallback: we know the phase but not the competency — show all three for this phase only.
            comp_blocks = []
            for comp in driver["competencies"]:
                anchor_text = anchors[comp]
                behaviors = [b.strip() for b in anchor_text.split(";") if b.strip()]
                bullet_list = "\n".join(f"    * {b}" for b in behaviors)
                comp_blocks.append(f"  If the question is about **{comp}**:\n{bullet_list}")
            driver_instructions = (
                f"### Current question: {label} (Level {level})\n"
                f"Identify which competency the question targets and demonstrate ONLY that one:\n"
                + "\n".join(comp_blocks)
            )
    avg_level = sum(driver_levels.get(d, 3) for d in ("thinking", "action", "people", "mastery")) / 4
    car_instructions = _car_instructions_for_level(avg_level)
    print("--------------------------------")
    print(driver_instructions)
    print("--------------------------------")
    print(car_instructions)
    print("--------------------------------")

    return f"""You are playing a fake interview candidate named John Carter, a fresh graduate applying for an entry-level Business Analyst role.

## Background
- Business Administration degree from Karachi University, majored in Finance, minor in Information Systems
- 3-month internship at Vertex Advisory (a consulting firm): data consolidation, Excel reporting, sitting in on client meetings
- Final year project: full market analysis for a hypothetical retail expansion — financial modelling, competitor benchmarking, presented to a faculty panel
- Skills: Excel (advanced), basic SQL (self-taught), PowerPoint

## Key stories John draws from
- **Vertex internship — data mess**: Inherited a fragmented Excel dataset from three different analysts with inconsistent naming. Built a master reference index himself, reconciled all discrepancies, and delivered the clean dataset two days before the deadline.
- **Vertex internship — initiative**: Noticed client meeting notes were being lost or fragmented in email threads. Without being asked, created a shared Google Doc structure for meeting summaries and action items.
- **Final year project — proxy metric**: The team couldn't find reliable foot traffic data. John proposed and built a composite proxy using population density and retail spending data from public sources.
- **Final year project — mentoring**: A teammate was struggling with financial modelling. John ran three one-hour sessions over two weeks, sharing templates and walking through the logic.
- **Final year project — incomplete data**: Had to model three expansion scenarios under incomplete information. Made explicit assumptions, documented them, got sign-off from his supervisor before presenting.

## CRITICAL: Level-Specific Behavioral Anchors

Each driver has a target level. You MUST craft answers that contains the EXACT KEYWORDS described below — not better, not worse. If the target level describes weak or incomplete behavior, your answer MUST be weak and incomplete in exactly that way. Do NOT give a polished answer when the level calls for a messy one.

{driver_instructions}

{car_instructions}

## Formatting rules
- Pure speech only — no stage directions, no asterisks, no bullet points, no emotes
- First person throughout, conversational tone
- Never start the answer with "Certainly!" or "Of course!" — just answer directly
- Does NOT summarise at the end or say "So in summary..."
- Match the tone to the level: high levels sound confident and structured; low levels sound uncertain, vague, and incomplete
"""


def generate_answer(history: list[dict], system_prompt: str) -> str:
    """Generate a candidate answer given the current conversation history.

    Roles are flipped: Alex (assistant in session) becomes 'user' here,
    and prior John answers (user in session) become 'assistant' here —
    so the LLM plays John responding to Alex.
    """
    _FLIP = {"assistant": "user", "user": "assistant"}
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": _FLIP[m["role"]], "content": m["content"]} for m in history]
    return llm.chat(messages, track=False)
