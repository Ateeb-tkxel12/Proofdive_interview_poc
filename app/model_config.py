"""Per-agent model configuration.

Each agent gets its own model and optional temperature override.
Pricing is per-model so token cost calculations stay accurate.
"""

# Model assignments per agent label.
# The label matches the `label` parameter passed to llm.chat().
AGENT_MODELS = {
    # Orchestrator — needs strong reasoning for routing decisions.
    "orchestrator": {"model": "gpt-5.4", "temperature": None},

    # Candidate answer generation — needs strong reasoning to hit rubric behaviors.
    "candidate": {"model": "gpt-5.4", "temperature": None},

    # CAR evaluation — needs precision for JSON verdict.
    "car:thinking": {"model": "gpt-5.4", "temperature": None},
    "car:action": {"model": "gpt-5.4", "temperature": None},
    "car:people": {"model": "gpt-5.4", "temperature": None},
    "car:mastery": {"model": "gpt-5.4", "temperature": None},

    # Phase agents (drivers) — simpler task, mini model is sufficient.
    "agent:intro": {"model": "gpt-5.4-mini", "temperature": None},
    "agent:thinking": {"model": "gpt-5.4-mini", "temperature": None},
    "agent:action": {"model": "gpt-5.4-mini", "temperature": None},
    "agent:people": {"model": "gpt-5.4-mini", "temperature": None},
    "agent:mastery": {"model": "gpt-5.4-mini", "temperature": None},
    "agent:close": {"model": "gpt-5.4-mini", "temperature": None},

    # Report/evaluator — deterministic output, uses gpt-4o with temperature 0.
    "report": {"model": "gpt-5.4", "temperature": 0.0},
}

# Default model for any label not listed above.
DEFAULT_MODEL = {"model": "gpt-5.4-mini", "temperature": None}

# Pricing in USD per 1 million tokens, keyed by model name.
MODEL_PRICING = {
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

# Fallback pricing if model not found in MODEL_PRICING.
DEFAULT_PRICING = {"input": 1.00, "output": 5.00}
