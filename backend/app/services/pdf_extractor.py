"""Extract text from linked PDF spec sheets."""

from __future__ import annotations

import io

import httpx


async def extract_pdf_text(url: str, max_pages: int = 10) -> str:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
    except Exception:
        return ""

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for i, page in enumerate(reader.pages[:max_pages]):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
        return "\n\n".join(pages)
    except ImportError:
        return ""
    except Exception:
        return ""
