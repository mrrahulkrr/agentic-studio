import time
import os
from contextvars import ContextVar
from google import genai
from google.genai import types
from dotenv import load_dotenv
from app.core.config import CHAT_MODEL, EMBEDDING_MODEL, TIER_MODELS

load_dotenv()

current_model_overrides: ContextVar[dict[str, str]] = ContextVar("current_model_overrides", default={})

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_client = genai.Client(api_key=GEMINI_API_KEY)


class GeminiQuotaExhausted(Exception):
    """Raised by generate_text when Gemini returns 429/RESOURCE_EXHAUSTED.

    Not retried, unlike the 503/UNAVAILABLE case below: a retry can't out-wait
    a daily quota reset within one request's lifetime, so retrying would only
    burn the retry budget for no benefit. Never falls through to
    generate_text's generic "having trouble" fallback string either, since
    that string reads like a real (if apologetic) answer — the caller needs
    to know this specific call can't succeed against this model today.

    `tier` starts unset: the tier a call resolved to (FAST/STANDARD/QUALITY)
    is only known at the call site, not inside generate_text() itself, so
    generate_for_tier() attaches it on the way out rather than this class
    guessing it.
    """

    def __init__(self, model: str, original: Exception):
        self.model = model
        self.tier: str | None = None
        super().__init__(f"Gemini quota exhausted for model '{model}': {original}")


def embed_text(text: str, max_retries: int = 3) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")

    for attempt in range(max_retries):
        try:
            response = _client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=768),
            )
            return response.embeddings[0].values
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def generate_text(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    max_retries: int = 3,
    temperature: float = 0.2,
    response_json: bool = False,
) -> str:
    """`model` defaults to CHAT_MODEL when not given, for any caller that
    hasn't been migrated to a tier. Every call site in this codebase now
    goes through generate_for_tier() below instead of passing `model`
    directly — see its docstring for why."""
    if not user_prompt or not user_prompt.strip():
        raise ValueError("Cannot generate from empty prompt")
    resolved_model = model or CHAT_MODEL
    for attempt in range(max_retries):
        try:
            response = _client.models.generate_content(
                model=resolved_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    response_mime_type="application/json" if response_json else None,
                ),
            )
            return response.text
        except Exception as exc:
            message = str(exc)
            if "429" in message or "RESOURCE_EXHAUSTED" in message:
                # Checked before 503 below: distinct failure mode, must not
                # retry and must not degrade to the generic fallback string.
                raise GeminiQuotaExhausted(resolved_model, exc) from exc
            if "503" in message or "UNAVAILABLE" in message:
                if attempt == max_retries - 1:
                    return "I'm having trouble generating a response right now. Please try again."
                time.sleep(2 ** attempt)
                continue
            raise


def generate_for_tier(
    tier: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_retries: int = 3,
    temperature: float = 0.2,
    response_json: bool = False,
) -> str:
    """The one seam every tiered call site uses instead of calling
    generate_text() directly with a raw model string.

    Two things live here so none of the call sites repeat them:
      1. Resolving which model this tier actually uses this call — a
         caller-supplied override (already validated by the caller, e.g.
         main.py's /run-agent, against config.TIER_CANDIDATES — this
         function does not re-validate) or the tier's configured default
         from config.TIER_MODELS.
      2. Attaching `tier` to a GeminiQuotaExhausted exception on the way
         out. The tier is only known at the call site, never inside
         generate_text() itself, so this is the one place that needs to
         know both the tier and the exception.
    """
    overrides = current_model_overrides.get()
    model = overrides.get(tier, TIER_MODELS[tier])
    try:
        return generate_text(
            system_prompt,
            user_prompt,
            model=model,
            max_retries=max_retries,
            temperature=temperature,
            response_json=response_json,
        )
    except GeminiQuotaExhausted as exc:
        exc.tier = tier
        raise
