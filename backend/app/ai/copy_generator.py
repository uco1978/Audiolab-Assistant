import json
import re
from dataclasses import dataclass
from typing import Any

from app.ai.providers import completion, completion_with_fallback
from app.config import get_settings
from app.scrapers.generic import ScrapedProduct
from app.services.brand_tone import load_brand_context

SYSTEM_PROMPT = """You are a professional Hebrew e-commerce copywriter.
Write all customer-facing text in Modern Hebrew (עברית תקנית).
Product specifications may be provided in English — translate them accurately.
Match the brand tone shown in the examples when provided.
CRITICAL RULES:
- Use ONLY facts from the provided data. Never invent specifications.
- If a spec is missing, omit it. Do not guess.
- Return valid JSON only, no markdown fences."""

USER_PROMPT_TEMPLATE = """{brand_context}

Create Hebrew product page copy from this data:

Product: {title}
Brand: {brand}
SKU: {sku}
Description (source): {description}

Specifications:
{specs}

Return JSON with this exact structure:
{{
  "title_he": "Hebrew product title",
  "description_html_he": "<p>HTML body in Hebrew (no html/head/body tags)</p>",
  "short_description_he": "1-3 sentences or bullets in Hebrew",
  "promotional": {{
    "social": "Hebrew social media post",
    "ad_headline": "Hebrew ad headline",
    "ad_body": "Hebrew ad body text",
    "email_teaser": "Hebrew email teaser"
  }},
  "seo": {{
    "title": "Hebrew SEO title, max 40 chars",
    "description": "Hebrew meta description, max 120 chars",
    "keywords": ["keyword1", "keyword2"]
  }}
}}"""


@dataclass
class GeneratedCopy:
    model_id: str
    title_he: str
    description_html_he: str
    short_description_he: str
    promotional: dict[str, str]
    seo: dict[str, Any]
    raw_json: dict[str, Any]
    brand_notes: list[str]
    fallback_models_tried: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.fallback_models_tried is None:
            self.fallback_models_tried = []


def _format_specs(specs: dict[str, str]) -> str:
    if not specs:
        return "(none provided)"
    return "\n".join(f"- {k}: {v}" for k, v in specs.items())


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _wrap_ltr_codes(html: str) -> str:
    pattern = r"\b([A-Z]{1,5}[-\s]?[A-Z0-9./]{2,20})\b"

    def replacer(match: re.Match) -> str:
        code = match.group(1)
        if re.search(r"[\u0590-\u05FF]", code):
            return code
        return f'<span dir="ltr">{code}</span>'

    return re.sub(pattern, replacer, html)


def _build_messages(product: ScrapedProduct) -> tuple[list[dict[str, str]], list[str]]:
    brand_context, brand_notes = load_brand_context()
    user_prompt = USER_PROMPT_TEMPLATE.format(
        brand_context=brand_context or "(No brand examples yet — use professional retail Hebrew.)",
        title=product.title,
        brand=product.brand,
        sku=product.sku,
        description=product.description[:2000],
        specs=_format_specs(product.specs),
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return messages, brand_notes


def _parse_copy(raw_text: str, model_id: str, product: ScrapedProduct, brand_notes: list[str], fallback_tried: list[str] | None = None) -> GeneratedCopy:
    data = _extract_json(raw_text)
    description = _wrap_ltr_codes(data.get("description_html_he", ""))
    return GeneratedCopy(
        model_id=model_id,
        title_he=data.get("title_he", product.title),
        description_html_he=description,
        short_description_he=data.get("short_description_he", ""),
        promotional=data.get("promotional", {}),
        seo=data.get("seo", {}),
        raw_json=data,
        brand_notes=brand_notes,
        fallback_models_tried=fallback_tried or [],
    )


async def generate_copy_with_model(product: ScrapedProduct, model_id: str) -> GeneratedCopy:
    """Generate copy using a specific model. Raises on failure (no fallback)."""
    messages, brand_notes = _build_messages(product)
    raw_text = await completion(model_id, messages)
    return _parse_copy(raw_text, model_id, product, brand_notes)


async def generate_copy(product: ScrapedProduct) -> GeneratedCopy:
    """Generate copy using the fallback chain."""
    settings = get_settings()
    messages, brand_notes = _build_messages(product)
    raw_text, used_model, _tried = await completion_with_fallback(settings.default_model_ids, messages)
    return _parse_copy(raw_text, used_model, product, brand_notes, _tried)
