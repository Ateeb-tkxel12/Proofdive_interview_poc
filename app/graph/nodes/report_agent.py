"""Report Agent — produces the final evaluation report in one LLM call.

Reuses the existing evaluator rubric prompt (`app/prompts/evaluator/evaluator_system.prompt`)
and the transcript formatter in `app/services/evaluator`. Runs once at the end
of the interview.

Reads:   state["history"], state["config"]
Writes:  state["final_report"]
Routed from: orchestrator (action "report", after close_agent has spoken)
"""

import json
import logging
import re
from pathlib import Path

from app.graph.state import InterviewState
from app.services import llm
from app.services.evaluator import _format_transcript

logger = logging.getLogger(__name__)

_EVALUATOR_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "evaluator"
_PROMPT_PATH = _EVALUATOR_DIR / "evaluator_system.prompt"
_RUBRIC_PATH = _EVALUATOR_DIR / "rubric.json"


def report_agent(state: InterviewState) -> dict:
    logger.info("[REPORT_AGENT] compiling final report  history_len=%d", len(state.get("history", [])))
    cfg = state["config"]

    # Competency info is stored in the assistant history entries by phase_agents,
    # so _format_transcript reads it directly.
    transcript = _format_transcript(state["history"])

    # Pass the rubric JSON directly to the LLM — no formatting needed,
    # LLMs read structured JSON well.
    rubric_json = _RUBRIC_PATH.read_text()

    system = (
        _PROMPT_PATH.read_text()
        .replace("{{MODE}}", cfg.get("mode", "FG"))
        .replace("{{ROLE}}", cfg.get("role", "Unknown"))
        .replace("{{RUBRIC}}", rubric_json)
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            "Evaluate this interview transcript and return the JSON report.\n\n"
            f"## Transcript\n\n{transcript}"
        )},
    ]

    raw = llm.chat(messages, label="report")

    # Parse JSON, stripping any accidental code fences. Errors get surfaced in
    # a wrapper dict so the UI can display them instead of crashing.
    try:
        cleaned = re.sub(r"```json\s*|```", "", raw)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            logger.error("[REPORT_AGENT] no JSON found in LLM output")
            return {"final_report": {"error": True, "message": "No JSON in report output.", "raw": raw}}
        report = json.loads(match.group())
        logger.info("[REPORT_AGENT] done  overall_score=%s  label=%s",
                     report.get("overall_score"), report.get("overall_label"))
        return {"final_report": report}
    except json.JSONDecodeError as e:
        logger.error("[REPORT_AGENT] JSON parse error: %s", e)
        return {"final_report": {"error": True, "message": f"JSON parse error: {e}", "raw": raw}}
    except Exception as e:
        logger.error("[REPORT_AGENT] error: %s", e)
        return {"final_report": {"error": True, "message": str(e), "raw": raw}}
