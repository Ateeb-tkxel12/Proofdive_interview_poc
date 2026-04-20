"""Per-agent model configuration.

Change the model variables below to swap models across all agents that use them.
"""

# ── Model variables (change these to swap models) ──
ORCHESTRATOR_MODEL = "gpt-5.4"
CANDIDATE_MODEL = "gpt-5.4-mini"
PHASE_MODEL = "gpt-5.4-mini"
CAR_MODEL = "gpt-5.4-mini"
EVIDENCE_MODEL = "gpt-5.4-mini"
SCORER_MODEL = "gpt-5.4"
SCORER_TEMP = 0.0
REPORT_MODEL = "gpt-5.4-mini"

# ── Agent model assignments ──
AGENT_MODELS = {
    # Orchestrator
    "orchestrator": {"model": ORCHESTRATOR_MODEL, "temperature": None},

    # Candidate answer generation
    "candidate": {"model": CANDIDATE_MODEL, "temperature": None},

    # CAR evaluation
    "car:thinking": {"model": CAR_MODEL, "temperature": None},
    "car:action": {"model": CAR_MODEL, "temperature": None},
    "car:people": {"model": CAR_MODEL, "temperature": None},
    "car:mastery": {"model": CAR_MODEL, "temperature": None},

    # Phase agents (drivers)
    "agent:intro": {"model": PHASE_MODEL, "temperature": None},
    "agent:thinking": {"model": PHASE_MODEL, "temperature": None},
    "agent:action": {"model": PHASE_MODEL, "temperature": None},
    "agent:people": {"model": PHASE_MODEL, "temperature": None},
    "agent:mastery": {"model": PHASE_MODEL, "temperature": None},
    "agent:close": {"model": PHASE_MODEL, "temperature": None},

    # Evidence extractor
    "evidence_extractor": {"model": EVIDENCE_MODEL, "temperature": None},

    # Per-driver scorer
    "scorer:thinking": {"model": SCORER_MODEL, "temperature": SCORER_TEMP},
    "scorer:action": {"model": SCORER_MODEL, "temperature": SCORER_TEMP},
    "scorer:people": {"model": SCORER_MODEL, "temperature": SCORER_TEMP},
    "scorer:mastery": {"model": SCORER_MODEL, "temperature": SCORER_TEMP},

    # Report narrative writer
    "report": {"model": REPORT_MODEL, "temperature": None},
}

# Default model for any label not listed above.
DEFAULT_MODEL = {"model": PHASE_MODEL, "temperature": None}

# ── Pricing per 1M tokens ──
MODEL_PRICING = {
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

DEFAULT_PRICING = {"input": 1.00, "output": 5.00}
