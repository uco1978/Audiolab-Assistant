from __future__ import annotations

from pathlib import Path

from app.ai.providers import completion_with_fallback
from app.config import get_settings
from app.services.brand_tone import read_brand_file
from app.services.training_corpus import load_corpus_summary


def _collect_corpus_samples(max_files: int = 20, max_chars_per_file: int = 2500) -> list[str]:
    from app.services.training_corpus import ensure_local_uploaded_corpus

    ensure_local_uploaded_corpus()
    summary = load_corpus_summary()
    if not summary:
        raise FileNotFoundError("No corpus scan found. Upload product-copy files first on the Training page.")

    usable = [item for item in summary.items if item.status == "usable"]
    if not usable:
        raise ValueError("No usable corpus files found. Upload product-copy files first.")

    samples: list[str] = []
    for item in usable[:max_files]:
        text = read_brand_file(Path(item.path)).strip()
        if not text:
            continue
        clipped = text[:max_chars_per_file]
        samples.append(f"### Source: {item.filename}\n{clipped}")
    if not samples:
        raise ValueError("Could not load text samples from usable corpus files.")
    return samples


async def generate_style_guide_from_corpus(max_files: int = 20) -> dict:
    settings = get_settings()
    samples = _collect_corpus_samples(max_files=max_files)

    prompt = (
        "You are a Hebrew brand-voice analyst. Analyze the writing samples and produce a concise "
        "STYLE GUIDE for product-page copywriting.\n\n"
        "Output requirements:\n"
        "- Plain text (no code fences)\n"
        "- Hebrew-oriented e-commerce style\n"
        "- Actionable, specific rules\n"
        "- Keep it concise: 350-700 words\n"
        "- Structure exactly with these section headers:\n"
        "1) Brand Voice Summary\n"
        "2) Tone Rules\n"
        "3) Structure Rules\n"
        "4) Vocabulary Preferences\n"
        "5) Formatting Rules\n"
        "6) Do / Don't\n"
        "7) Reusable Phrases\n\n"
        "Prioritize patterns repeated across samples, not one-off quirks.\n\n"
        "SAMPLES:\n\n"
        + "\n\n".join(samples)
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You extract stable writing style patterns from copywriting corpora and turn them "
                "into practical style guides."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    guide_text, model_used, _ = await completion_with_fallback(settings.default_model_ids, messages)

    guide_text = guide_text.strip()
    if guide_text.startswith("```"):
        guide_text = guide_text.strip("`").strip()
        if guide_text.lower().startswith("text"):
            guide_text = guide_text[4:].strip()

    style_path = settings.brand_examples_dir / "style-guide.txt"
    style_path.parent.mkdir(parents=True, exist_ok=True)
    style_path.write_text(guide_text + "\n", encoding="utf-8")

    if settings.storage_backend.lower() == "s3":
        try:
            from app.storage import get_storage

            get_storage().upload_file(style_path, "brand/style-guide.txt")
        except Exception:
            # Local style guide is enough for current runtime; R2 persist is best-effort.
            pass

    return {
        "ok": True,
        "style_guide_path": str(style_path),
        "model_used": model_used,
        "samples_used": len(samples),
        "content": guide_text,
    }
