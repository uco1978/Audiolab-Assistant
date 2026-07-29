"""
Select main product images using heuristics + cloud LLM metadata ranking.
"""

from __future__ import annotations

import base64
import io
import json
import re

import httpx
from PIL import Image

from app.ai.providers import completion_with_fallback
from app.config import get_settings
from app.scrapers.generic import ScrapedImage

MAX_CANDIDATES_FOR_AI = 20
MAX_FOR_VISION = 8
MAX_PRODUCT_IMAGES = 8

POSITIVE_CONTEXT = (
    "product", "gallery", "hero", "zoom", "main", "pdp", "carousel", "swiper",
    "media", "image", "photo", "primary", "featured", "magnifier", "lightbox",
)
NEGATIVE_CONTEXT = (
    "logo", "icon", "banner", "footer", "header", "nav", "navigation", "menu",
    "related", "upsell", "cross-sell", "accessory", "badge", "rating", "star",
    "payment", "visa", "paypal", "social", "facebook", "twitter", "avatar",
    "sprite", "advert", "promo", "newsletter", "cookie", "breadcrumb",
)
NEGATIVE_URL = (
    "logo", "icon", "sprite", "pixel", "badge", "avatar", "payment", "social",
    "banner", "advert", "1x1", "spacer", "blank", "placeholder", "tracking",
)


def score_heuristic(img: ScrapedImage) -> float:
    score = 0.0
    url_lower = img.url.lower()
    alt_lower = (img.alt or "").lower()
    ctx_lower = (img.context or "").lower()
    combined = f"{url_lower} {alt_lower} {ctx_lower}"

    if img.source == "json_ld":
        score += 50
    elif img.source == "open_graph":
        score += 35

    for word in POSITIVE_CONTEXT:
        if word in combined:
            score += 8
    for word in NEGATIVE_CONTEXT:
        if word in combined:
            score -= 15
    for word in NEGATIVE_URL:
        if word in url_lower:
            score -= 20

    if img.width and img.height:
        area = img.width * img.height
        if area > 500_000:
            score += 15
        elif area > 100_000:
            score += 8
        elif area < 40_000:
            score -= 10
        ratio = img.width / max(img.height, 1)
        if ratio > 4 or ratio < 0.2:
            score -= 12

    if re.search(r"\d{1,3}x\d{1,3}", url_lower):
        score -= 25

    img.heuristic_score = score
    return score


def filter_by_heuristics(images: list[ScrapedImage], min_score: float = -10) -> list[ScrapedImage]:
    scored = []
    for img in images:
        if score_heuristic(img) >= min_score:
            scored.append(img)
    scored.sort(key=lambda x: x.heuristic_score, reverse=True)
    return scored


async def _fetch_thumbnail_b64(url: str, max_size: int = 384) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            pil = Image.open(io.BytesIO(resp.content)).convert("RGB")
            pil.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            pil.save(buf, format="JPEG", quality=75)
            return base64.standard_b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


async def _rank_by_metadata_llm(product_title: str, candidates: list[ScrapedImage]) -> list[int]:
    settings = get_settings()
    items = [
        {
            "index": i,
            "url": img.url[:200],
            "alt": img.alt,
            "source": img.source,
            "context": img.context[:120],
            "heuristic_score": img.heuristic_score,
        }
        for i, img in enumerate(candidates)
    ]

    prompt = f"""Product: {product_title}

Select ONLY main product photos for an e-commerce listing.
EXCLUDE logos, icons, banners, UI, related products, payment badges.

Return JSON: {{"selected_indices": [0, 2, 5]}}

Candidates:
{json.dumps(items, ensure_ascii=False, indent=2)}"""

    try:
        raw, _, _tried = await completion_with_fallback(
            settings.default_model_ids,
            [
                {"role": "system", "content": "Filter product images. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        selected = json.loads(text).get("selected_indices", [])
        valid = [i for i in selected if isinstance(i, int) and 0 <= i < len(candidates)]
        if valid:
            return valid[:MAX_PRODUCT_IMAGES]
    except Exception:
        pass
    return list(range(min(len(candidates), MAX_PRODUCT_IMAGES)))


async def _vision_score_disabled(indices: list[int]) -> list[int]:
    # Vision-model scoring is disabled in cloud-only mode; keep metadata+heuristic order.
    return indices


async def select_product_images(
    images: list[ScrapedImage],
    product_title: str,
    use_ai: bool = True,
    use_vision: bool = True,
) -> tuple[list[ScrapedImage], list[str]]:
    notes: list[str] = []
    if not images:
        return [], notes

    filtered = filter_by_heuristics(images)
    notes.append(f"Heuristic filter: {len(images)} → {len(filtered)} candidates")

    if not filtered:
        filtered = sorted(images, key=score_heuristic, reverse=True)[:5]
        notes.append("Heuristic fallback: kept top 5 by score")

    pool = filtered[:MAX_CANDIDATES_FOR_AI]

    if not use_ai or len(pool) <= 2:
        return pool[:MAX_PRODUCT_IMAGES], notes + [f"Selected top {min(len(pool), MAX_PRODUCT_IMAGES)} by heuristics"]

    indices = await _rank_by_metadata_llm(product_title, pool)
    notes.append(f"Ollama text ranking: {len(indices)} candidates")

    if use_vision:
        indices = await _vision_score_disabled(indices)
        notes.append("Vision scoring disabled in cloud mode; using metadata ranking only")

    selected = [pool[i] for i in indices if i < len(pool)]
    if not selected:
        selected = pool[:MAX_PRODUCT_IMAGES]
        notes.append("AI empty; heuristic fallback")
    return selected, notes
