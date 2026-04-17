import logging

from openai import OpenAI

from app.config import OPENAI_API_KEY
from app.model_config import AGENT_MODELS, DEFAULT_MODEL, DEFAULT_PRICING, MODEL_PRICING

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _resolve_model(label: str) -> tuple[str, float | None]:
    """Look up the model and temperature for a given agent label."""
    config = AGENT_MODELS.get(label, DEFAULT_MODEL)
    return config["model"], config.get("temperature")


def _get_pricing(model: str) -> dict:
    """Get per-million-token pricing for a model."""
    return MODEL_PRICING.get(model, DEFAULT_PRICING)


_total_tokens: int = 0
_token_log: list[dict] = []


def reset_tokens() -> None:
    global _total_tokens, _token_log
    _total_tokens = 0
    _token_log = []


def get_total_tokens() -> int:
    return _total_tokens


def get_token_log() -> list[dict]:
    return list(_token_log)


def cost_for_tokens(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a given model + token split."""
    pricing = _get_pricing(model)
    return (
        input_tokens / 1_000_000 * pricing["input"]
        + output_tokens / 1_000_000 * pricing["output"]
    )


def summarize_log(log: list[dict], label_filter=None) -> dict:
    """Aggregate a token log (optionally filtered by a predicate on label)
    into {prompt, completion, total, cost_usd}."""
    keep = log if label_filter is None else [e for e in log if label_filter(e["label"])]
    prompt = sum(e["prompt"] for e in keep)
    completion = sum(e["completion"] for e in keep)
    cost = sum(e.get("cost", 0.0) for e in keep)
    return {
        "prompt": prompt,
        "completion": completion,
        "total": prompt + completion,
        "cost_usd": cost,
    }


def chat(messages: list[dict], track: bool = True, label: str = "") -> str:
    """Call the LLM using the Responses API and return the response text.

    The model and temperature are resolved from model_config.py based on
    the label (e.g. "orchestrator", "agent:thinking", "report").
    """
    global _total_tokens

    model, temperature = _resolve_model(label)
    logger.info("[LLM] calling  label=%s  model=%s  messages=%d", label, model, len(messages))

    # Split messages into system instruction + conversation turns.
    instructions = None
    input_items = []
    for msg in messages:
        if msg["role"] == "system":
            if instructions is None:
                instructions = msg["content"]
            else:
                instructions += "\n\n" + msg["content"]
        else:
            input_items.append({"role": msg["role"], "content": msg["content"]})

    if not input_items:
        input_items = instructions or ""
        instructions = None

    # Build the API call kwargs.
    kwargs = {
        "model": model,
        "instructions": instructions,
        "input": input_items,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    response = _get_client().responses.create(**kwargs)
    content = response.output_text

    preview = content[:150].replace("\n", " ")
    if len(content) > 150:
        preview += "..."
    logger.info("[LLM] done  label=%s  model=%s  response=%s", label, model, preview)

    if track and response.usage is not None:
        usage = response.usage
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        total = input_tokens + output_tokens
        cost = cost_for_tokens(model, input_tokens, output_tokens)
        _total_tokens += total
        _token_log.append({
            "label": label,
            "model": model,
            "prompt": input_tokens,
            "completion": output_tokens,
            "total": total,
            "cost": cost,
        })
        logger.info("[LLM] tokens  in=%d  out=%d  cost=$%.4f  model=%s",
                     input_tokens, output_tokens, cost, model)

    return content
