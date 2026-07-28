"""Web search enrichment for product specifications."""

from __future__ import annotations

from urllib.parse import urlparse

from app.config import get_settings


async def enrich_product_specs(
    product_name: str,
    manufacturer_domain: str,
    existing_specs: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    notes: list[str] = []
    specs = dict(existing_specs)

    tavily_results = await _search_tavily(product_name, manufacturer_domain)
    if tavily_results:
        notes.append(f"Tavily returned {len(tavily_results)} results")
        for r in tavily_results:
            snippet = r.get("content", "")
            _merge_snippet_specs(specs, snippet)

    ddg_results = await _search_duckduckgo(product_name, manufacturer_domain)
    if ddg_results:
        notes.append(f"DuckDuckGo returned {len(ddg_results)} results")
        for snippet in ddg_results:
            _merge_snippet_specs(specs, snippet)

    return specs, notes


async def _search_tavily(query: str, domain: str) -> list[dict]:
    settings = get_settings()
    if not settings.tavily_api_key:
        return []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": f'"{query}" specifications site:{domain}',
                    "max_results": 5,
                },
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
    except Exception:
        return []


async def _search_duckduckgo(query: str, domain: str) -> list[str]:
    try:
        from duckduckgo_search import DDGS

        full_query = f"{query} specifications site:{domain}"
        with DDGS() as ddgs:
            results = list(ddgs.text(full_query, max_results=5))
        return [r.get("body", "") for r in results if r.get("body")]
    except Exception:
        return []


def _merge_snippet_specs(specs: dict[str, str], snippet: str) -> None:
    for line in snippet.replace(";", "\n").split("\n"):
        line = line.strip()
        if ":" in line and len(line) < 200:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if key and val and key not in specs:
                specs[key] = val


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc
