"""Brand-specific scraper plugins for known manufacturer sites."""

from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers.generic import ScrapedProduct, parse_product_html


def get_brand_plugin(url: str):
    host = urlparse(url).netloc.lower()
    if "bosch" in host:
        return _enhance_bosch
    if "dewalt" in host:
        return _enhance_dewalt
    return None


def apply_brand_plugin(url: str, html: str, product: ScrapedProduct) -> ScrapedProduct:
    plugin = get_brand_plugin(url)
    if not plugin:
        return product
    return plugin(url, html, product)


def _enhance_bosch(url: str, html: str, product: ScrapedProduct) -> ScrapedProduct:
    soup = BeautifulSoup(html, "lxml")
    for section in soup.select("[class*='specification'], [class*='technical'], [data-testid*='spec']"):
        for row in section.find_all(["tr", "li"]):
            text = row.get_text(" ", strip=True)
            if ":" in text:
                k, _, v = text.partition(":")
                if k.strip() and v.strip():
                    product.specs.setdefault(k.strip(), v.strip())
    product.source_notes.append("Applied Bosch brand plugin")
    return product


def _enhance_dewalt(url: str, html: str, product: ScrapedProduct) -> ScrapedProduct:
    soup = BeautifulSoup(html, "lxml")
    for spec in soup.select(".product-specs li, .specifications tr"):
        text = spec.get_text(" ", strip=True)
        if ":" in text:
            k, _, v = text.partition(":")
            product.specs.setdefault(k.strip(), v.strip())
    product.source_notes.append("Applied DeWalt brand plugin")
    return product
