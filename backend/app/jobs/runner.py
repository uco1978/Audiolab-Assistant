import asyncio
import logging
import tempfile
import time
from pathlib import Path

from app.ai.copy_generator import generate_copy, generate_copy_with_model
from app.config import get_settings
from app.db import append_progress, update_job
from app.models import JobProgressEvent, JobStatus, JobStep
from app.scrapers.brand_plugins import apply_brand_plugin
from app.scrapers.generic import fetch_page_html, product_slug, scrape_product
from app.scrapers.playwright_fetch import fetch_with_playwright
from app.services.exporter import export_product
from app.services.image_downloader import download_images
from app.services.image_processor import process_image
from app.services.image_selector import select_product_images
from app.services.pdf_extractor import extract_pdf_text
from app.services.web_search import domain_from_url, enrich_product_specs
from app.storage import get_storage


def _pick_two_models(settings) -> list[str]:
    """Pick up to 2 configured models from different providers."""
    seen_providers: set[str] = set()
    picked: list[str] = []
    for model_id in settings.default_model_ids:
        if not settings.model_is_configured(model_id):
            continue
        provider = model_id.split("/")[0] if "/" in model_id else model_id
        if provider in seen_providers:
            continue
        seen_providers.add(provider)
        picked.append(model_id)
        if len(picked) == 2:
            break
    if len(picked) < 2:
        for m in settings.available_models:
            mid = m["id"]
            if mid in picked or not settings.model_is_configured(mid):
                continue
            provider = m["provider"]
            if provider in seen_providers:
                continue
            seen_providers.add(provider)
            picked.append(mid)
            if len(picked) == 2:
                break
    return picked


async def run_job(job_id: str, url: str, config: dict) -> None:
    settings = get_settings()
    await update_job(job_id, status=JobStatus.RUNNING.value)
    job_t0 = time.perf_counter()
    timing: dict[str, int] = {}

    try:
        await _progress(job_id, JobStep.VALIDATE, "Validating cloud AI configuration", 5)

        html: str | None = None
        use_playwright = config.get("use_playwright", False) and settings.playwright_enabled

        t0 = time.perf_counter()
        await _progress(job_id, JobStep.SCRAPE, "Fetching product page", 15)
        try:
            html = await fetch_page_html(url)
        except Exception:
            if use_playwright:
                html = await fetch_with_playwright(url)
            else:
                raise

        product = await scrape_product(url, html=html)

        if use_playwright and len(product.images) < 1:
            await _progress(job_id, JobStep.SCRAPE, "Retrying with Playwright", 20)
            html = await fetch_with_playwright(url)
            product = await scrape_product(url, html=html)

        product = apply_brand_plugin(url, html or "", product)

        if config.get("web_search"):
            await _progress(job_id, JobStep.SEARCH, "Enriching specs from web", 30)
            domain = domain_from_url(url)
            product.specs, search_notes = await enrich_product_specs(
                product.title, domain, product.specs
            )
            product.source_notes.extend(search_notes)

        if product.pdf_links:
            for pdf_url in product.pdf_links[:3]:
                text = await extract_pdf_text(pdf_url)
                if text:
                    product.source_notes.append(f"PDF extracted: {pdf_url}")
                    for line in text.split("\n"):
                        if ":" in line and len(line) < 200:
                            k, _, v = line.partition(":")
                            k, v = k.strip(), v.strip()
                            if k and v and k not in product.specs:
                                product.specs[k] = v
        timing["scrape_ms"] = int((time.perf_counter() - t0) * 1000)

        slug = product_slug(product)
        work_dir = Path(tempfile.mkdtemp(prefix=f"ppc-local-{slug}-"))
        raw_images_dir = work_dir / "raw-images"
        processed_images_dir = work_dir / "processed-images"

        t0 = time.perf_counter()
        use_ai_images = config.get("ai_image_selection", True)
        await _progress(job_id, JobStep.DOWNLOAD_IMAGES, "Selecting product images (local AI)", 40)
        selected_images, image_notes = await select_product_images(
            product.images,
            product.title,
            use_ai=use_ai_images,
            use_vision=use_ai_images,
        )
        product.images = selected_images
        product.source_notes.extend(image_notes)

        await _progress(job_id, JobStep.DOWNLOAD_IMAGES, "Downloading images", 48)
        downloaded = await download_images(product.images, raw_images_dir)

        await _progress(job_id, JobStep.PROCESS_IMAGES, "Processing images to WebP", 58)
        rembg_flag = config.get("rembg_enabled")
        if rembg_flag is None:
            rembg_flag = settings.rembg_default_for_jobs
        processed = []
        total_imgs = max(len(downloaded), 1)
        for idx, dl in enumerate(downloaded, start=1):
            pct = 58 + int(10 * (idx - 1) / total_imgs)
            await _progress(
                job_id,
                JobStep.PROCESS_IMAGES,
                f"Processing image {idx}/{len(downloaded)}"
                + (" (rembg)" if rembg_flag else ""),
                pct,
            )
            processed.append(
                process_image(dl, processed_images_dir, idx, rembg_enabled=rembg_flag)
            )
        timing["images_ms"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()

        # Pick 2 models from different providers for comparison
        model_candidates = _pick_two_models(settings)
        copies = []
        all_fallback: list[str] = []

        if len(model_candidates) >= 2:
            await _progress(job_id, JobStep.GENERATE_COPY,
                f"Generating Hebrew copy with {len(model_candidates)} models in parallel", 65)
            tasks = [generate_copy_with_model(product, m) for m in model_candidates]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logging.getLogger("ppc.runner").warning("Variant generation failed: %s", r)
                else:
                    copies.append(r)

        if not copies:
            await _progress(job_id, JobStep.GENERATE_COPY,
                "Generating Hebrew copy (fallback chain)", 72)
            fallback_copy = await generate_copy(product)
            copies = [fallback_copy]
            all_fallback = fallback_copy.fallback_models_tried

        for c in copies:
            product.source_notes.extend(c.brand_notes)

        compare_mode = len(copies) > 1
        timing["ai_copy_ms"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        await _progress(job_id, JobStep.EXPORT, "Exporting product folder", 90)
        product_dir = export_product(
            output_root=Path(settings.output_dir),
            slug=slug,
            product=product,
            processed_images=processed,
            copies=copies,
            compare_mode=compare_mode,
        )

        storage_prefix: str | None = None
        if settings.storage_backend.lower() == "s3":
            storage_prefix = f"jobs/{job_id}"
            get_storage().upload_directory(product_dir, storage_prefix)
        timing["export_ms"] = int((time.perf_counter() - t0) * 1000)
        timing["total_ms"] = int((time.perf_counter() - job_t0) * 1000)

        from app.services.exporter import _variant_id
        variant_ids = [_variant_id(c.model_id) for c in copies] if compare_mode else []

        await update_job(
            job_id,
            status=JobStatus.COMPLETED.value,
            product_slug=slug,
            output_path=str(product_dir),
            storage_prefix=storage_prefix,
            models_used=[c.model_id for c in copies],
            variants=variant_ids,
            timing=timing,
            fallback_models=all_fallback,
        )
        await _progress(job_id, JobStep.DONE, "Complete", 100, {"output_path": str(product_dir)})

    except Exception as exc:
        timing["total_ms"] = int((time.perf_counter() - job_t0) * 1000)
        await update_job(job_id, status=JobStatus.FAILED.value, error=str(exc), timing=timing)
        await _progress(job_id, JobStep.DONE, f"Failed: {exc}", 100)


async def _progress(
    job_id: str,
    step: JobStep,
    message: str,
    percent: int,
    detail: dict | None = None,
) -> None:
    await append_progress(
        job_id,
        JobProgressEvent(step=step, message=message, percent=percent, detail=detail),
    )
