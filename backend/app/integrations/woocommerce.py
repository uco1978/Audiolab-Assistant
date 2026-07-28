"""
WooCommerce REST API integration.

Phase 3: create draft products from exported manifest.json folders.
See docs/manifest-schema.md for field mapping.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


class WooCommerceClient:
    def __init__(self, site_url: str, consumer_key: str, consumer_secret: str):
        self.site_url = site_url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.api_base = f"{self.site_url}/wp-json/wc/v3"

    async def create_draft_product(self, product_dir: Path, category_id: int | None = None) -> dict:
        manifest = json.loads((product_dir / "manifest.json").read_text(encoding="utf-8"))
        wc = manifest.get("woocommerce", {})

        description = _read_optional(product_dir / wc.get("description_file", ""))
        short_desc = _read_optional(product_dir / wc.get("short_description_file", ""))
        if not description:
            html_path = product_dir / "copy" / "product-description.html"
            description = _read_optional(html_path)
        if not short_desc:
            short_path = product_dir / "copy" / "short-description.txt"
            short_desc = _read_optional(short_path)

        body_html = _extract_body(description)

        payload: dict[str, Any] = {
            "name": wc.get("name") or manifest.get("slug", "Product"),
            "type": "simple",
            "status": wc.get("status", "draft"),
            "description": body_html,
            "short_description": short_desc,
            "attributes": [
                {"name": a["name"], "visible": True, "options": [a["value"]]}
                for a in wc.get("attributes", [])
            ],
        }
        if category_id:
            payload["categories"] = [{"id": category_id}]

        images = manifest.get("images", [])
        if images:
            payload["images"] = await self._prepare_images(product_dir, images)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.api_base}/products",
                auth=(self.consumer_key, self.consumer_secret),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def _prepare_images(self, product_dir: Path, images: list[dict]) -> list[dict]:
        result = []
        async with httpx.AsyncClient(timeout=120) as client:
            for img in images:
                file_path = product_dir / img["file"]
                if not file_path.exists():
                    continue
                media = await self._upload_media(client, file_path, img.get("alt", ""))
                if media:
                    result.append({"id": media["id"], "alt": img.get("alt", "")})
        return result

    async def _upload_media(self, client: httpx.AsyncClient, path: Path, alt: str) -> dict | None:
        content = path.read_bytes()
        headers = {
            "Content-Disposition": f'attachment; filename="{path.name}"',
            "Content-Type": "image/webp",
        }
        resp = await client.post(
            f"{self.site_url}/wp-json/wp/v2/media",
            auth=(self.consumer_key, self.consumer_secret),
            content=content,
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            return None
        media = resp.json()
        if alt and media.get("id"):
            await client.post(
                f"{self.site_url}/wp-json/wp/v2/media/{media['id']}",
                auth=(self.consumer_key, self.consumer_secret),
                json={"alt_text": alt},
            )
        return media


def _read_optional(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _extract_body(html: str) -> str:
    if "<body" in html:
        start = html.lower().find("<body")
        end = html.lower().find("</body>")
        if start != -1 and end != -1:
            fragment = html[start:end]
            open_end = fragment.find(">") + 1
            return fragment[open_end:]
    return html


async def sync_product_to_woocommerce(
    product_dir: Path,
    site_url: str,
    consumer_key: str,
    consumer_secret: str,
    category_id: int | None = None,
    status: str = "draft",
) -> dict:
    client = WooCommerceClient(site_url, consumer_key, consumer_secret)
    manifest_path = product_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("woocommerce", {})["status"] = status
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return await client.create_draft_product(product_dir, category_id=category_id)
