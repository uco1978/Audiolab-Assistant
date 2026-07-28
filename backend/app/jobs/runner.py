import tempfile
from pathlib import Path

from app.ai.copy_generator import generate_copy
from app.ai.ollama_client import ensure_model_pulled, ollama_health, unload_model
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


async def run_job(job_id: str, url: str, config: dict) -> None:
    settings = get_settings()
    await update_job(job_id, status=JobStatus.RUNNING.value)

    try:
        await _progress(job_id, JobStep.VALIDATE, "Checking Ollama", 3)
        health = await ollama_health()
        if not health["ok"]:
            raise RuntimeError(
                "Ollama is not running. Start Ollama, then run: ollama pull qwen2.5:7b-instruct"
            )

        await _progress(job_id, JobStep.VALIDATE, "Ensuring local models are ready", 5)
        if not await ensure_model_pulled(settings.text_model):
            raise RuntimeError(f"Could not pull text model: {settings.text_model}")
        if config.get("ai_image_selection", True):
            await ensure_model_pulled(settings.vision_model)

        html: str | None = None
        use_playwright = config.get("use_playwright", False) and settings.playwright_enabled

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

        slug = product_slug(product)
        work_dir = Path(tempfile.mkdtemp(prefix=f"ppc-local-{slug}-"))
        raw_images_dir = work_dir / "raw-images"
        processed_images_dir = work_dir / "processed-images"

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
        processed = [
            process_image(dl, processed_images_dir, idx, rembg_enabled=config.get("rembg_enabled"))
            for idx, dl in enumerate(downloaded, start=1)
        ]

        await _progress(
            job_id,
            JobStep.GENERATE_COPY,
            f"Generating Hebrew copy ({settings.text_model})",
            72,
        )
        copy = await generate_copy(product)
        product.source_notes.extend(copy.brand_notes)
        await unload_model(settings.text_model)

        await _progress(job_id, JobStep.EXPORT, "Exporting product folder", 90)
        product_dir = export_product(
            output_root=Path(settings.output_dir),
            slug=slug,
            product=product,
            processed_images=processed,
            copies=[copy],
            compare_mode=False,
        )

        storage_prefix: str | None = None
        if settings.storage_backend.lower() == "s3":
            storage_prefix = f"jobs/{job_id}"
            get_storage().upload_directory(product_dir, storage_prefix)

        await update_job(
            job_id,
            status=JobStatus.COMPLETED.value,
            product_slug=slug,
            output_path=str(product_dir),
            storage_prefix=storage_prefix,
            models_used=[copy.model_id],
            variants=[],
        )
        await _progress(job_id, JobStep.DONE, "Complete", 100, {"output_path": str(product_dir)})

    except Exception as exc:
        await update_job(job_id, status=JobStatus.FAILED.value, error=str(exc))
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
