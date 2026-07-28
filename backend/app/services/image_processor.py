import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.services.image_downloader import DownloadedImage


@dataclass
class ProcessedImage:
    webp_path: Path
    original_path: Path
    alt: str
    width: int
    height: int
    has_alpha: bool
    needs_review: bool
    review_reason: str | None = None


_rembg_session = None


def _get_rembg_session():
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session

        _rembg_session = new_session("u2net")
    return _rembg_session


def _has_meaningful_alpha(img: Image.Image) -> bool:
    if img.mode not in ("RGBA", "LA", "PA"):
        return False
    alpha = img.split()[-1]
    extrema = alpha.getextrema()
    return extrema[0] < 250


def _remove_background(img: Image.Image) -> Image.Image:
    from rembg import remove

    session = _get_rembg_session()
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    result = remove(buf.getvalue(), session=session)
    return Image.open(io.BytesIO(result)).convert("RGBA")


def _score_quality(original: Image.Image, processed: Image.Image) -> tuple[bool, str | None]:
    orig_pixels = original.width * original.height
    proc_pixels = processed.width * processed.height
    if proc_pixels < orig_pixels * 0.5:
        return False, "Significant content may have been removed"
    alpha = processed.split()[-1]
    transparent_ratio = sum(1 for p in alpha.getdata() if p < 10) / len(alpha.getdata())
    if transparent_ratio < 0.05:
        return False, "Background removal produced little transparency"
    if transparent_ratio > 0.95:
        return False, "Nearly entire image is transparent"
    return True, None


def process_image(
    downloaded: DownloadedImage,
    dest_dir: Path,
    index: int,
    rembg_enabled: bool | None = None,
) -> ProcessedImage:
    settings = get_settings()
    use_rembg = settings.rembg_enabled if rembg_enabled is None else rembg_enabled

    dest_dir.mkdir(parents=True, exist_ok=True)
    original = Image.open(downloaded.original_path)
    working = original.convert("RGBA")

    needs_review = False
    review_reason = None

    if _has_meaningful_alpha(working):
        processed = working
    elif use_rembg:
        try:
            processed = _remove_background(original)
            ok, reason = _score_quality(original, processed)
            if not ok:
                needs_review = True
                review_reason = reason
        except Exception as exc:
            processed = working
            needs_review = True
            review_reason = f"Background removal failed: {exc}"
    else:
        processed = working
        needs_review = True
        review_reason = "No transparency and rembg disabled"

    prefix = "01-hero" if index == 1 else f"{index:02d}-gallery"
    webp_path = dest_dir / f"{prefix}.webp"
    processed.save(webp_path, format="WEBP", quality=settings.webp_quality, method=6)

    return ProcessedImage(
        webp_path=webp_path,
        original_path=downloaded.original_path,
        alt=downloaded.alt,
        width=processed.width,
        height=processed.height,
        has_alpha=_has_meaningful_alpha(processed),
        needs_review=needs_review,
        review_reason=review_reason,
    )
