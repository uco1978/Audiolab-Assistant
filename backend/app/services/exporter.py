import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ai.copy_generator import GeneratedCopy
from app.scrapers.generic import ScrapedProduct
from app.services.image_processor import ProcessedImage

RTL_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
</head>
<body>
{body}
</body>
</html>
"""


def _variant_id(model_id: str) -> str:
    return model_id.replace("/", "-").replace(":", "-")


def export_product(
    output_root: Path,
    slug: str,
    product: ScrapedProduct,
    processed_images: list[ProcessedImage],
    copies: list[GeneratedCopy],
    compare_mode: bool,
) -> Path:
    product_dir = output_root / slug
    copy_dir = product_dir / "copy"
    images_dir = product_dir / "images"
    specs_dir = product_dir / "specs"
    raw_dir = product_dir / "raw"

    for d in (copy_dir, images_dir, specs_dir, raw_dir, raw_dir / "images-original"):
        d.mkdir(parents=True, exist_ok=True)

    (raw_dir / "page.html").write_text(product.raw_html, encoding="utf-8")
    scraped_data = {
        "url": product.url,
        "title": product.title,
        "brand": product.brand,
        "sku": product.sku,
        "description": product.description,
        "specs": product.specs,
        "pdf_links": product.pdf_links,
        "source_notes": product.source_notes,
        "robots_allowed": product.robots_allowed,
        "robots_warning": product.robots_warning,
    }
    (raw_dir / "scraped-data.json").write_text(
        json.dumps(scraped_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for img in processed_images:
        shutil.copy2(img.webp_path, images_dir / img.webp_path.name)
        if img.original_path.exists():
            shutil.copy2(img.original_path, raw_dir / "images-original" / img.original_path.name)

    _write_specs(specs_dir, product)

    variants: list[str] = []
    primary: GeneratedCopy | None = None

    if compare_mode and len(copies) > 1:
        for copy in copies:
            vid = _variant_id(copy.model_id)
            variants.append(vid)
            vdir = copy_dir / "variants" / vid
            _write_copy_files(vdir, copy)
    elif copies:
        primary = copies[0]
        _write_copy_files(copy_dir, primary)
        for copy in copies[1:]:
            vid = _variant_id(copy.model_id)
            variants.append(vid)
            _write_copy_files(copy_dir / "variants" / vid, copy)

    manifest = _build_manifest(
        slug=slug,
        product=product,
        processed_images=processed_images,
        primary=primary or (copies[0] if copies else None),
        variants=variants,
        compare_mode=compare_mode,
    )
    (product_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return product_dir


def _write_copy_files(directory: Path, copy: GeneratedCopy) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    html = RTL_HTML_TEMPLATE.format(title=copy.title_he, body=copy.description_html_he)
    (directory / "product-description.html").write_text(html, encoding="utf-8")
    (directory / "short-description.txt").write_text(copy.short_description_he, encoding="utf-8")

    promo_lines = [
        "## רשתות חברתיות",
        copy.promotional.get("social", ""),
        "",
        "## כותרת מודעה",
        copy.promotional.get("ad_headline", ""),
        "",
        "## גוף מודעה",
        copy.promotional.get("ad_body", ""),
        "",
        "## טיזר אימייל",
        copy.promotional.get("email_teaser", ""),
    ]
    (directory / "promotional-copy.md").write_text("\n".join(promo_lines), encoding="utf-8")
    (directory / "seo-meta.json").write_text(
        json.dumps(copy.seo, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_specs(specs_dir: Path, product: ScrapedProduct) -> None:
    lines = ["# מפרט טכני", "", "| מפרט | ערך |", "|------|------|"]
    for k, v in product.specs.items():
        lines.append(f"| {k} | {v} |")
    (specs_dir / "spec-sheet.md").write_text("\n".join(lines), encoding="utf-8")

    with open(specs_dir / "spec-sheet.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["spec", "value"])
        for k, v in product.specs.items():
            writer.writerow([k, v])

    notes = ["# מקורות", ""] + [f"- {n}" for n in product.source_notes]
    if product.robots_warning:
        notes.append(f"- Warning: {product.robots_warning}")
    (specs_dir / "source-notes.md").write_text("\n".join(notes), encoding="utf-8")


def _build_manifest(
    slug: str,
    product: ScrapedProduct,
    processed_images: list[ProcessedImage],
    primary: GeneratedCopy | None,
    variants: list[str],
    compare_mode: bool,
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "slug": slug,
        "locale": "he",
        "direction": "rtl",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_url": product.url,
        "woocommerce": {
            "name": primary.title_he if primary else product.title,
            "description_file": "copy/product-description.html",
            "short_description_file": "copy/short-description.txt",
            "status": "draft",
            "attributes": [{"name": k, "value": v} for k, v in product.specs.items()],
        },
        "seo": primary.seo if primary else {},
        "images": [
            {
                "file": f"images/{img.webp_path.name}",
                "alt": img.alt or (primary.title_he if primary else product.title),
                "format": "webp",
                "has_alpha": img.has_alpha,
                "needs_review": img.needs_review,
                "review_reason": img.review_reason,
            }
            for img in processed_images
        ],
        "variants": variants,
        "compare_mode": compare_mode,
        "primary_model": primary.model_id if primary else None,
    }


def promote_variant(product_dir: Path, variant_id: str) -> None:
    copy_dir = product_dir / "copy"
    variant_dir = copy_dir / "variants" / variant_id
    if not variant_dir.exists():
        raise FileNotFoundError(f"Variant not found: {variant_id}")

    for name in (
        "product-description.html",
        "short-description.txt",
        "promotional-copy.md",
        "seo-meta.json",
    ):
        src = variant_dir / name
        if src.exists():
            shutil.copy2(src, copy_dir / name)

    manifest_path = product_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["primary_model"] = variant_id
        seo_path = variant_dir / "seo-meta.json"
        if seo_path.exists():
            manifest["seo"] = json.loads(seo_path.read_text(encoding="utf-8"))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
