import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup


@dataclass
class ScrapedImage:
    url: str
    alt: str = ""
    width: int | None = None
    height: int | None = None
    source: str = "dom"  # json_ld | open_graph | dom
    context: str = ""  # parent DOM hints, e.g. class names
    heuristic_score: float = 0.0


@dataclass
class ScrapedProduct:
    url: str
    title: str = ""
    description: str = ""
    brand: str = ""
    sku: str = ""
    images: list[ScrapedImage] = field(default_factory=list)
    specs: dict[str, str] = field(default_factory=dict)
    pdf_links: list[str] = field(default_factory=list)
    raw_html: str = ""
    source_notes: list[str] = field(default_factory=list)
    robots_allowed: bool = True
    robots_warning: str | None = None


async def check_robots(url: str) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(robots_url)
            if resp.status_code != 200:
                return True, None
            rp.parse(resp.text.splitlines())
        allowed = rp.can_fetch("*", url)
        if not allowed:
            return False, f"robots.txt disallows fetching {url}"
        return True, None
    except Exception:
        return True, None


async def fetch_page_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _parse_json_ld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Product":
                return item
            graph = item.get("@graph", [])
            for node in graph:
                if isinstance(node, dict) and node.get("@type") == "Product":
                    return node
    return {}


def _extract_og(soup: BeautifulSoup) -> dict[str, str]:
    og: dict[str, str] = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name") or ""
        if prop.startswith("og:") or prop in ("title", "description"):
            content = meta.get("content", "")
            if content:
                og[prop] = content
    return og


def _extract_specs_from_tables(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                if key and val:
                    specs[key] = val
    return specs


def _extract_specs_from_dl(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            key = dt.get_text(strip=True)
            val = dd.get_text(strip=True)
            if key and val:
                specs[key] = val
    return specs


def _extract_specs_from_lists(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for ul in soup.find_all(["ul", "ol"]):
        parent_class = " ".join(ul.get("class", []))
        if not any(k in parent_class.lower() for k in ("spec", "feature", "detail")):
            continue
        for li in ul.find_all("li", recursive=False):
            text = li.get_text(strip=True)
            if ":" in text:
                key, _, val = text.partition(":")
                specs[key.strip()] = val.strip()
    return specs


def _normalize_image_url(base_url: str, src: str) -> str | None:
    if not src or src.startswith("data:"):
        return None
    return urljoin(base_url, src)


def _parse_srcset(srcset: str) -> list[tuple[str, int]]:
    candidates: list[tuple[str, int]] = []
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split()
        url = pieces[0]
        width = 0
        if len(pieces) > 1 and pieces[1].endswith("w"):
            try:
                width = int(pieces[1][:-1])
            except ValueError:
                width = 0
        candidates.append((url, width))
    return candidates


def _parent_context(img_tag) -> str:
    parts: list[str] = []
    for parent in img_tag.parents:
        if parent.name in ("div", "section", "figure", "li", "ul", "main", "article"):
            cls = " ".join(parent.get("class", []))[:60]
            pid = (parent.get("id") or "")[:40]
            label = parent.name
            if cls:
                label += f".{cls}"
            if pid:
                label += f"#{pid}"
            parts.append(label)
            if len(parts) >= 4:
                break
    return " > ".join(parts)


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[ScrapedImage]:
    seen: set[str] = set()
    images: list[ScrapedImage] = []

    def add(
        url: str | None,
        alt: str = "",
        w: int | None = None,
        h: int | None = None,
        source: str = "dom",
        context: str = "",
    ) -> None:
        if not url:
            return
        full = _normalize_image_url(base_url, url)
        if not full or full in seen:
            return
        seen.add(full)
        images.append(
            ScrapedImage(url=full, alt=alt, width=w, height=h, source=source, context=context)
        )

    product = _parse_json_ld(soup)
    for img in product.get("image", []) if isinstance(product.get("image"), list) else [product.get("image")]:
        if isinstance(img, str):
            add(img, source="json_ld", context="schema.org Product.image")
        elif isinstance(img, dict):
            add(
                img.get("url") or img.get("contentUrl"),
                img.get("name", ""),
                source="json_ld",
                context="schema.org Product.image",
            )

    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        add(og_image["content"], source="open_graph", context="og:image")

    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        ctx = _parent_context(img)
        srcset = img.get("srcset", "")
        if srcset:
            best = max(_parse_srcset(srcset), key=lambda x: x[1], default=None)
            if best:
                add(best[0], alt, source="dom", context=ctx)
                continue
        add(img.get("src") or img.get("data-src") or img.get("data-lazy-src"), alt, source="dom", context=ctx)

    return images


def _extract_pdf_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    pdfs: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            full = urljoin(base_url, href)
            if full not in pdfs:
                pdfs.append(full)
    return pdfs


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80].strip("-")


def parse_product_html(url: str, html: str) -> ScrapedProduct:
    soup = BeautifulSoup(html, "lxml")
    json_ld = _parse_json_ld(soup)
    og = _extract_og(soup)

    title = (
        json_ld.get("name")
        or og.get("og:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else "")
    )
    description = (
        json_ld.get("description")
        or og.get("og:description")
        or og.get("description")
        or ""
    )
    brand = ""
    brand_data = json_ld.get("brand")
    if isinstance(brand_data, dict):
        brand = brand_data.get("name", "")
    elif isinstance(brand_data, str):
        brand = brand_data

    sku = json_ld.get("sku") or json_ld.get("mpn") or ""

    specs = {}
    specs.update(_extract_specs_from_tables(soup))
    specs.update(_extract_specs_from_dl(soup))
    specs.update(_extract_specs_from_lists(soup))

    additional = json_ld.get("additionalProperty", [])
    if isinstance(additional, list):
        for prop in additional:
            if isinstance(prop, dict):
                name = prop.get("name", "")
                value = prop.get("value", "")
                if name and value:
                    specs[str(name)] = str(value)

    images = _extract_images(soup, url)
    pdf_links = _extract_pdf_links(soup, url)

    notes = [f"Primary source: {url}"]
    if json_ld:
        notes.append("Extracted JSON-LD Product schema")
    if og:
        notes.append("Extracted Open Graph metadata")

    return ScrapedProduct(
        url=url,
        title=str(title or "product"),
        description=str(description or ""),
        brand=str(brand or ""),
        sku=str(sku or ""),
        images=images,
        specs=specs,
        pdf_links=pdf_links,
        raw_html=html,
        source_notes=notes,
    )


async def scrape_product(url: str, html: str | None = None) -> ScrapedProduct:
    allowed, warning = await check_robots(url)
    if html is None:
        html = await fetch_page_html(url)
    product = parse_product_html(url, html)
    product.robots_allowed = allowed
    product.robots_warning = warning
    return product


def product_slug(product: ScrapedProduct) -> str:
    base = product.title or product.sku or "product"
    if product.brand:
        base = f"{product.brand}-{base}"
    return _slugify(base)
