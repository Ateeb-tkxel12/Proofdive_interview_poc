"""Report Agent — three-step evaluation pipeline.

Step 1: Evidence Extractor — extracts direct candidate quotes per driver.
Step 2: Scorer — classifies level per driver (one LLM call per driver).
Step 3: Report Writer — generates narrative sections (strengths, areas, coaching).

Python handles score computation (averages, labels, pass/fail) — not the LLM.

Reads:   state["history"], state["config"]
Writes:  state["final_report"]
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
_EXTRACTOR_PROMPT_PATH = _EVALUATOR_DIR / "evidence_extractor.prompt"
_SCORER_PROMPT_PATH = _EVALUATOR_DIR / "scorer.prompt"
_REPORT_PROMPT_PATH = _EVALUATOR_DIR / "evaluator_system.prompt"
_RUBRIC_PATH = _EVALUATOR_DIR / "rubric.json"

_DRIVER_SUBLABELS = {
    "thinking": "Analytical depth & structure",
    "action": "Ownership & execution",
    "people": "Collaboration & communication",
    "mastery": "Execution & technical clarity",
}


def _parse_json(raw: str) -> dict | None:
    """Extract and parse JSON from an LLM response."""
    cleaned = re.sub(r"```json\s*|```", "", raw).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    return None


# ── Step 1: Extract evidence ──

def _extract_evidence(transcript: str) -> dict:
    logger.info("[REPORT] step 1: extracting evidence")
    system = _EXTRACTOR_PROMPT_PATH.read_text()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Extract direct quotes from this transcript:\n\n{transcript}"},
    ]
    raw = llm.chat(messages, label="evidence_extractor")
    logger.info("[REPORT] evidence:\n%s", raw)
    parsed = _parse_json(raw)
    return parsed or {"drivers": {}}


# ── Step 2: Score each driver ──

def _build_competency_rubric(rubric: dict, driver_key: str, competency: str) -> str:
    """Extract just the relevant competency's levels from the rubric."""
    driver = rubric["drivers"].get(driver_key, {})
    levels = driver.get("levels", {})
    lines = []
    for level in ("5", "4", "3", "2", "1"):
        anchor = levels.get(level, {}).get(competency, "")
        lines.append(f"Level {level}: {anchor}")
    return "\n".join(lines)


def _score_driver(driver_key: str, evidence: dict, rubric: dict) -> dict:
    """Score a single driver by calling the scorer LLM."""
    competency = evidence.get("competency", "")
    quotes = evidence.get("quotes", [])
    quotes_text = "\n".join(f'- "{q}"' for q in quotes)

    logger.info("[REPORT] step 2: scoring %s (%s)", driver_key, competency)

    competency_rubric = _build_competency_rubric(rubric, driver_key, competency)
    system = (
        _SCORER_PROMPT_PATH.read_text()
        .replace("{{COMPETENCY}}", competency)
        .replace("{{COMPETENCY_RUBRIC}}", competency_rubric)
        .replace("{{QUOTES}}", quotes_text)
    )

    messages = [
        {"role": "system", "content": system},
    ]

    raw = llm.chat(messages, label=f"scorer:{driver_key}")
    parsed = _parse_json(raw)

    if parsed and "level" in parsed:
        logger.info("[REPORT] scored %s: level=%s  why=%s",
                     driver_key, parsed["level"], parsed.get("why", ""))
        return parsed

    logger.warning("[REPORT] scorer failed for %s, defaulting to 1.0", driver_key)
    return {"level": 1.0, "anchor_label": "Fragmented", "why": "Could not parse scorer output",
            "missing_for_next": None}


# ── Step 3: Python computes scores ──

def _compute_scores(driver_scores: dict[str, dict]) -> dict:
    """Compute overall score, label, pass/fail from per-driver levels. Pure Python."""
    scores = {}
    for driver_key in ("thinking", "action", "people", "mastery"):
        ds = driver_scores.get(driver_key, {})
        scores[driver_key] = {
            "score": float(ds.get("level", 1.0)),
            "anchor_label": ds.get("anchor_label", ""),
            "sublabel": _DRIVER_SUBLABELS.get(driver_key, ""),
            "coaching_tip": ds.get("missing_for_next") or "Continue developing at this level.",
        }

    driver_vals = [s["score"] for s in scores.values()]
    overall = round(sum(driver_vals) / len(driver_vals), 1)

    if overall >= 4.5:
        label, sublabel = "Star", "Exemplary"
    elif overall >= 3.5:
        label = "Ready"
        sublabel = "Strong" if min(driver_vals) >= 3.5 else "With Improvements"
    elif overall >= 2.5:
        label, sublabel = "Borderline", "Needs Work" if min(driver_vals) < 2.5 else "Developing"
    else:
        label, sublabel = "Not Yet", "Significant Gaps"

    passed = overall >= 3.5 and min(driver_vals) >= 2.5
    role_model = max(driver_vals) >= 5.0

    return {
        "overall_score": overall,
        "overall_label": label,
        "overall_sublabel": sublabel,
        "pass": passed,
        "conduct_clear": True,
        "conduct_quote": None,
        "role_model": role_model,
        "drivers": scores,
    }


# ── Step 4: Generate narrative ──

def _generate_narrative(computed: dict, evidence: dict, cfg: dict) -> dict:
    """LLM generates strengths, areas, coaching, verdict based on scores + evidence."""
    logger.info("[REPORT] step 3: generating narrative")

    system = (
        _REPORT_PROMPT_PATH.read_text()
        .replace("{{MODE}}", cfg.get("mode", "FG"))
        .replace("{{ROLE}}", cfg.get("role", "Unknown"))
        .replace("{{SCORES}}", json.dumps(computed, indent=2))
        .replace("{{EVIDENCE}}", json.dumps(evidence, indent=2))
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Generate the narrative sections of the report."},
    ]

    raw = llm.chat(messages, label="report")
    return _parse_json(raw) or {}


# ── Main entry point ──

def report_agent(state: InterviewState) -> dict:
    logger.info("[REPORT] compiling final report  history_len=%d", len(state.get("history", [])))
    cfg = state["config"]
    transcript = _format_transcript(state["history"])
    rubric = json.loads(_RUBRIC_PATH.read_text())

    # Step 1: Extract direct quotes from transcript.
    evidence = _extract_evidence(transcript)
    drivers_evidence = evidence.get("drivers", {})

    # Step 2: Score each driver independently.
    driver_scores = {}
    for driver_key in ("thinking", "action", "people", "mastery"):
        if driver_key in drivers_evidence:
            driver_scores[driver_key] = _score_driver(driver_key, drivers_evidence[driver_key], rubric)
        else:
            logger.warning("[REPORT] no evidence for %s, defaulting to 1.0", driver_key)
            driver_scores[driver_key] = {"level": 1.0, "anchor_label": "", "why": "No evidence",
                                          "missing_for_next": None}

    # Step 3: Python computes overall score, label, pass/fail.
    computed = _compute_scores(driver_scores)

    # Step 4: LLM generates narrative sections.
    narrative = _generate_narrative(computed, evidence, cfg)

    # Merge: Python-computed scores + LLM-generated narrative.
    report = {**computed}
    report["overall_summary"] = narrative.get("overall_summary", "")
    report["car_analysis"] = narrative.get("car_analysis", {})
    report["car_insight"] = narrative.get("car_insight", "")
    report["strengths"] = narrative.get("strengths", [])
    report["areas"] = narrative.get("areas", [])
    report["question_insights"] = narrative.get("question_insights", [])
    report["coaching_cards"] = narrative.get("coaching_cards", [])
    report["hiring_readiness"] = narrative.get("hiring_readiness", {})
    report["final_verdict_title"] = narrative.get("final_verdict_title", "")
    report["final_verdict_body"] = narrative.get("final_verdict_body", "")

    logger.info("[REPORT] done  overall=%.1f  label=%s", report["overall_score"], report["overall_label"])
    return {"final_report": report}
