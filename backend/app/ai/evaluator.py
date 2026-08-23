from app.core.llm import generate_for_tier
import json
import re

from app.schemas import EvalResult


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(fenced)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError(f"Could not parse JSON from response: {text[:200]}")


def score_faithfulness(
    script_text: str, agent_result: str, model_override: str | None = None
) -> EvalResult:
    prompt = f"""Compare this analysis against the source script. Rate 1-10 how well the
analysis is grounded in the actual script content, versus making unsupported claims.

Script: {script_text}

Analysis: {agent_result}

Respond ONLY with JSON: {{"score": <number>, "reasoning": "<why>"}}"""

    # Deliberately still a single broad except, quota exhaustion included: an
    # optional eval score failing must never take down an already-successful
    # primary result. GeminiQuotaExhausted still gets `tier` attached (see
    # generate_for_tier) before landing here — it's just that this call site's
    # own contract, unlike main.py's run-agent path, is to never propagate any
    # failure past itself, and that isn't something this task changes.
    try:
        response = generate_for_tier(
            "QUALITY",
            "You are an evaluation system. Respond only with valid JSON.",
            prompt,
            model_override=model_override,
            temperature=0.0,
            response_json=True,
        )
        data = _parse_json_response(response)
        return EvalResult(score=data.get("score"), reasoning=data.get("reasoning", ""))
    except Exception:
        return EvalResult(score=None, reasoning="Could not parse evaluation response.")
