import io
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image

from app.scrapers.generic import ScrapedImage


@dataclass
class DownloadedImage:
    source_url: str
    alt: str
    original_path: Path
    width: int
    height: int


MIN_WIDTH = 200
MIN_HEIGHT = 200


async def download_images(
    images: list[ScrapedImage],
    dest_dir: Path,
) -> list[DownloadedImage]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[DownloadedImage] = []
    headers = {"User-Agent": "Mozilla/5.0 ProductPageCreator/1.0"}

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        for idx, img in enumerate(images, start=1):
            try:
                resp = await client.get(img.url)
                resp.raise_for_status()
                data = resp.content
                pil = Image.open(io.BytesIO(data))
                w, h = pil.size
                if w < MIN_WIDTH or h < MIN_HEIGHT:
                    continue
                ext = _ext_from_content_type(resp.headers.get("content-type", ""), img.url)
                filename = f"{idx:02d}-original{ext}"
                path = dest_dir / filename
                path.write_bytes(data)
                results.append(
                    DownloadedImage(
                        source_url=img.url,
                        alt=img.alt,
                        original_path=path,
                        width=w,
                        height=h,
                    )
                )
            except Exception:
                continue
    return results


def _ext_from_content_type(content_type: str, url: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    for ct, ext in mapping.items():
        if ct in content_type:
            return ext
    url_lower = url.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if url_lower.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return ".jpg"
