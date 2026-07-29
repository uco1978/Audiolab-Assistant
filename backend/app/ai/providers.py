import asyncio
import os
import time
from typing import Any

from app.config import get_settings
from app.db import record_ai_failure, record_ai_usage


def _configure_litellm_env() -> None:
    settings = get_settings()
    if settings.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
    if settings.groq_api_key:
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
    if settings.openrouter_api_key:
        os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    if settings.cohere_api_key:
        os.environ["COHERE_API_KEY"] = settings.cohere_api_key
    if settings.mistral_api_key:
        os.environ["MISTRAL_API_KEY"] = settings.mistral_api_key
    if settings.perplexity_api_key:
        os.environ["PERPLEXITY_API_KEY"] = settings.perplexity_api_key
    if settings.xai_api_key:
        os.environ["XAI_API_KEY"] = settings.xai_api_key


def provider_from_model(model_id: str) -> str:
    if model_id.startswith("gemini/"):
        return "gemini"
    if model_id.startswith("groq/"):
        return "groq"
    if model_id.startswith("openrouter/"):
        return "openrouter"
    if model_id.startswith("openai/"):
        return "openai"
    if model_id.startswith("anthropic/"):
        return "anthropic"
    if model_id.startswith("cohere/"):
        return "cohere"
    if model_id.startswith("mistral/"):
        return "mistral"
    if model_id.startswith("perplexity/"):
        return "perplexity"
    if model_id.startswith("xai/"):
        return "xai"
    return "unknown"


def litellm_model_name(model_id: str) -> str:
    # Keep internal model ids provider-qualified, but pass provider-native names to LiteLLM where needed.
    if model_id.startswith("openrouter/"):
        return model_id.replace("openrouter/", "", 1)
    return model_id


async def completion(
    model_id: str,
    messages: list[dict[str, str]],
    response_format: dict | None = None,
) -> str:
    import litellm

    _configure_litellm_env()
    kwargs: dict[str, Any] = {
        "model": litellm_model_name(model_id),
        "messages": messages,
        "temperature": 0.3,
    }
    if response_format:
        kwargs["response_format"] = response_format

    t0 = time.perf_counter()
    response = await litellm.acompletion(**kwargs)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    content = response.choices[0].message.content or ""
    provider = provider_from_model(model_id)
    usage = response.usage
    total_tokens = getattr(usage, "total_tokens", 0) if usage else len(content) // 4
    p_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    c_tokens = getattr(usage, "completion_tokens", None) if usage else None
    await record_ai_usage(provider, model_id, total_tokens, latency_ms, p_tokens, c_tokens)
    return content


async def test_provider_connection(provider: str, api_key: str | None = None, model_id: str | None = None) -> dict[str, Any]:
    provider = provider.strip().lower()
    settings = get_settings()
    if provider not in settings.provider_key_fields:
        raise RuntimeError(f"Unsupported provider: {provider}")

    if model_id:
        candidates = [model_id]
    elif provider == "openrouter":
        candidates = [
            "openrouter/openrouter/free",
            "openrouter/openrouter/auto",
            "openrouter/google/gemma-2-9b-it:free",
        ]
    elif provider == "gemini":
        candidates = [
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.0-flash",
        ]
    elif provider == "openai":
        candidates = ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]
    elif provider == "anthropic":
        candidates = ["anthropic/claude-3-5-haiku-latest", "anthropic/claude-3-5-sonnet-latest"]
    elif provider == "cohere":
        candidates = ["cohere/command-r-plus-08-2024", "cohere/command-r7b-12-2024"]
    elif provider == "mistral":
        candidates = ["mistral/mistral-large-latest", "mistral/mistral-small-latest"]
    elif provider == "perplexity":
        candidates = ["perplexity/sonar-pro", "perplexity/sonar"]
    elif provider == "xai":
        candidates = ["xai/grok-2-1212"]
    else:
        candidates = []
        for item in settings.available_models:
            if item["provider"] == provider:
                candidates.append(item["id"])
                break
    if not candidates:
        raise RuntimeError(f"No model configured for provider: {provider}")

    env_key_map = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "cohere": "COHERE_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "xai": "XAI_API_KEY",
    }
    env_key = env_key_map[provider]
    fallback_val = os.environ.get(env_key)
    settings_key = getattr(settings, f"{provider}_api_key", "")
    candidate_key = (api_key or "").strip() or settings_key.strip()
    if not candidate_key:
        raise RuntimeError(f"Missing API key for provider: {provider}")

    os.environ[env_key] = candidate_key
    try:
        last_error: Exception | None = None
        for model in candidates:
            try:
                content = await completion(
                    model,
                    [{"role": "user", "content": "Reply with OK only."}],
                )
                return {"ok": True, "provider": provider, "model_id": model, "response": content[:60]}
            except Exception as exc:
                last_error = exc
                continue
        msg = compact_error_message(last_error) if last_error else "Unknown provider test error"
        lower = msg.lower()
        if "429" in lower or "quota" in lower or "rate" in lower:
            raise RuntimeError(
                f"{provider} key is valid, but current quota/rate limit is exhausted for tested models. Details: {msg}"
            )
        if "404" in lower or "not found" in lower or "unavailable" in lower:
            raise RuntimeError(
                f"{provider} key is valid, but the tested model is unavailable for this account tier. Details: {msg}"
            )
        raise RuntimeError(msg)
    finally:
        if fallback_val is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = fallback_val


def classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "429" in msg or "rate" in msg or "quota" in msg:
        return "RateLimit"
    if "401" in msg or "auth" in msg or "invalid api key" in msg or "invalid x-api-key" in msg:
        return "AuthError"
    if "404" in msg or "not found" in msg or "unavailable" in msg or "does not exist" in msg:
        return "ModelUnavailable"
    if "timeout" in msg or "timed out" in msg:
        return "Timeout"
    if "content_filter" in msg or "content filter" in msg or "safety" in msg:
        return "ContentFilter"
    return "Unknown"


async def completion_with_fallback(
    model_ids: list[str],
    messages: list[dict[str, str]],
    response_format: dict | None = None,
) -> tuple[str, str, list[str]]:
    """Returns (content, winning_model_id, fallback_models_tried)."""
    settings = get_settings()
    chain = [p.strip() for p in settings.model_fallback_chain.split(",") if p.strip()]
    ordered = list(model_ids)
    for provider in chain:
        for model in settings.available_models:
            if model["provider"] == provider and model["id"] not in ordered:
                if settings.model_is_configured(model["id"]):
                    ordered.append(model["id"])

    last_error: Exception | None = None
    tried: list[str] = []
    for model_id in ordered:
        if not settings.model_is_configured(model_id):
            continue
        try:
            content = await completion(model_id, messages, response_format)
            return content, model_id, tried
        except Exception as exc:
            last_error = exc
            tried.append(model_id)
            t0_fail = time.perf_counter()
            err_class = classify_error(exc)
            latency = int((time.perf_counter() - t0_fail) * 1000) or 1
            await record_ai_failure(provider_from_model(model_id), model_id, latency, err_class)
            if _is_rate_limit(exc):
                await asyncio.sleep(2)
            continue
    raise RuntimeError(f"All configured cloud models failed. Last error: {last_error}")


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "quota" in msg


def compact_error_message(exc: Exception, max_len: int = 240) -> str:
    text = " ".join(str(exc).split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
