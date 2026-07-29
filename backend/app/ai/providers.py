import asyncio
import os
from typing import Any

from app.config import get_settings
from app.db import record_ai_usage


def _configure_litellm_env() -> None:
    settings = get_settings()
    if settings.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
    if settings.groq_api_key:
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
    if settings.openrouter_api_key:
        os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key


def provider_from_model(model_id: str) -> str:
    if model_id.startswith("gemini/"):
        return "gemini"
    if model_id.startswith("groq/"):
        return "groq"
    if model_id.startswith("openrouter/"):
        return "openrouter"
    return "unknown"


async def completion(
    model_id: str,
    messages: list[dict[str, str]],
    response_format: dict | None = None,
) -> str:
    import litellm

    _configure_litellm_env()
    kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.3,
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content or ""
    provider = provider_from_model(model_id)
    tokens = getattr(response.usage, "total_tokens", 0) if response.usage else len(content) // 4
    await record_ai_usage(provider, model_id, tokens)
    return content


async def completion_with_fallback(
    model_ids: list[str],
    messages: list[dict[str, str]],
    response_format: dict | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    chain = [p.strip() for p in settings.model_fallback_chain.split(",") if p.strip()]
    ordered = list(model_ids)
    for provider in chain:
        for model in settings.available_models:
            if model["provider"] == provider and model["id"] not in ordered:
                if settings.model_is_configured(model["id"]):
                    ordered.append(model["id"])

    last_error: Exception | None = None
    for model_id in ordered:
        if not settings.model_is_configured(model_id):
            continue
        try:
            return await completion(model_id, messages, response_format), model_id
        except Exception as exc:
            last_error = exc
            if _is_rate_limit(exc):
                await asyncio.sleep(2)
            continue
    raise RuntimeError(f"All configured cloud models failed. Last error: {last_error}")


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "quota" in msg
