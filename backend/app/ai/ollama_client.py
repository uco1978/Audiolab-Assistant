"""Ollama HTTP client for local text + vision inference."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.config import get_settings
from app.db import record_ai_usage


def _base_url() -> str:
    return get_settings().ollama_base_url.rstrip("/")


async def ollama_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{_base_url()}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return {"ok": True, "models": models}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "models": []}


async def ensure_model_pulled(model: str) -> bool:
    health = await ollama_health()
    if not health["ok"]:
        return False
    if any(model in m or m.startswith(model) for m in health["models"]):
        return True
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{_base_url()}/api/pull",
                json={"name": model, "stream": False},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def unload_model(model: str) -> None:
    """Free RAM between vision and text stages on 32GB laptops."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{_base_url()}/api/generate",
                json={"model": model, "keep_alive": 0},
            )
    except Exception:
        pass


async def text_completion(model: str, messages: list[dict[str, str]]) -> str:
    import litellm

    os.environ["OLLAMA_API_BASE"] = _base_url()
    response = await litellm.acompletion(
        model=f"ollama/{model}",
        messages=messages,
        temperature=0.3,
    )
    content = response.choices[0].message.content or ""
    await record_ai_usage("ollama", model, len(content) // 4)
    return content


async def vision_score(
    model: str,
    product_title: str,
    image_b64: str,
) -> tuple[float, bool]:
    prompt = (
        f'Product: "{product_title}"\n'
        "Rate this image as a main e-commerce product photo (0-10).\n"
        "10 = clean product shot, full product visible.\n"
        "0 = logo, icon, banner, unrelated.\n"
        'Return JSON only: {"score": 8, "is_product_photo": true}'
    )
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{_base_url()}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    score = float(data.get("score", 0))
    is_product = bool(data.get("is_product_photo", score >= 5))
    await record_ai_usage("ollama", model, 100)
    return score, is_product
