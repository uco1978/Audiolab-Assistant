"""Training corpus ingestion and Kaggle/Colab export helpers.

Phase 1 intentionally stops at dataset/package creation. Training itself runs
in a notebook on Kaggle/Colab or another GPU host.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from random import Random

from app.config import PROJECT_ROOT, get_settings
from app.services.brand_tone import BRAND_FILE_EXTENSIONS, read_brand_file
from app.storage import get_storage

TRAINING_DIR = PROJECT_ROOT / "data" / "training"
UPLOADED_CORPUS_DIR = TRAINING_DIR / "uploaded-corpus"
CORPUS_MANIFEST = TRAINING_DIR / "corpus-manifest.json"
DATASET_JSONL = TRAINING_DIR / "dataset.jsonl"
TRAIN_JSONL = TRAINING_DIR / "train.jsonl"
VALIDATION_JSONL = TRAINING_DIR / "validation.jsonl"
EXPORT_ZIP = TRAINING_DIR / "product-copy-training-package.zip"
EXPORT_STORAGE_KEY = TRAINING_DIR / "product-copy-training-package.storage-key"
CORPUS_STORAGE_PREFIX = "training/corpus"
CORPUS_INDEX_KEY = f"{CORPUS_STORAGE_PREFIX}/_index.json"

WORD_TEMP_PREFIX = "~$"
MIN_COPY_CHARS = 200
ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".html", ".docx"}


@dataclass
class CorpusItem:
    path: str
    filename: str
    title: str
    chars: int
    sha256: str
    status: str
    issue: str | None = None
    preview: str = ""
    duplicate_of: str | None = None


@dataclass
class CorpusSummary:
    folder_path: str
    scanned_at: str
    total_files: int
    usable_files: int
    duplicate_files: int
    issue_files: int
    items: list[CorpusItem]


def uploaded_corpus_dir() -> Path:
    UPLOADED_CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADED_CORPUS_DIR


def ensure_local_uploaded_corpus() -> Path:
    """Restore uploaded corpus from object storage when local disk is empty."""
    local_dir = uploaded_corpus_dir()
    existing = [p for p in local_dir.iterdir() if p.is_file() and not p.name.startswith(".")]
    if existing:
        return local_dir

    settings = get_settings()
    if settings.storage_backend.lower() != "s3":
        return local_dir

    storage = get_storage()
    try:
        index_raw = storage.read_bytes(CORPUS_INDEX_KEY).decode("utf-8")
        filenames = json.loads(index_raw).get("files", [])
    except Exception:
        return local_dir

    for name in filenames:
        safe = Path(name).name
        if Path(safe).suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
            continue
        try:
            data = storage.read_bytes(f"{CORPUS_STORAGE_PREFIX}/{safe}")
            (local_dir / safe).write_bytes(data)
        except Exception:
            continue
    return local_dir


def save_uploaded_corpus_files(files: list[tuple[str, bytes]], replace: bool = True) -> CorpusSummary:
    """Save uploaded corpus files locally (and to S3 when configured), then scan."""
    local_dir = uploaded_corpus_dir()
    if replace:
        for existing in local_dir.iterdir():
            if existing.is_file():
                existing.unlink()

    saved_names: list[str] = []
    for filename, content in files:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
            continue
        if safe_name.startswith(WORD_TEMP_PREFIX) or safe_name.startswith("."):
            continue
        if not content:
            continue
        target = local_dir / safe_name
        target.write_bytes(content)
        saved_names.append(safe_name)

    if not saved_names:
        raise ValueError("No valid files uploaded. Use .docx, .txt, .md, or .html files.")

    settings = get_settings()
    storage_warning: str | None = None
    if settings.storage_backend.lower() == "s3":
        try:
            storage = get_storage()
            for name in saved_names:
                storage.upload_file(local_dir / name, f"{CORPUS_STORAGE_PREFIX}/{name}")
            index_path = local_dir / "_index.json"
            index_path.write_text(
                json.dumps({"files": saved_names}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            storage.upload_file(index_path, CORPUS_INDEX_KEY)
            index_path.unlink(missing_ok=True)
        except Exception as exc:
            # Keep the local upload usable even if object-storage credentials are wrong.
            storage_warning = str(exc)

    summary = scan_corpus(str(local_dir))
    if storage_warning:
        # Attach a soft warning into notes via first usable item issue is too invasive;
        # callers that need it can check logs. For API clarity, raise only if local scan empty.
        import logging

        logging.getLogger("ppc.training").warning("Corpus R2 persist failed: %s", storage_warning)
    return summary


def scan_corpus(folder_path: str) -> CorpusSummary:
    folder = Path(folder_path).expanduser()
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Folder does not exist: {folder}")

    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    seen_hashes: dict[str, str] = {}
    items: list[CorpusItem] = []

    for path in sorted(folder.rglob("*")):
        if not _is_supported_file(path):
            continue

        try:
            text = read_brand_file(path)
        except Exception as exc:
            items.append(
                CorpusItem(
                    path=str(path),
                    filename=path.name,
                    title=_title_from_filename(path),
                    chars=0,
                    sha256="",
                    status="issue",
                    issue=f"Could not read file: {exc}",
                )
            )
            continue

        clean = _normalize_text(text)
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest() if clean else ""
        status = "usable"
        issue: str | None = None
        duplicate_of: str | None = None

        if len(clean) < MIN_COPY_CHARS:
            status = "issue"
            issue = f"Too short for training ({len(clean)} chars)"
        elif digest in seen_hashes:
            status = "duplicate"
            duplicate_of = seen_hashes[digest]
            issue = f"Duplicate of {Path(duplicate_of).name}"
        else:
            seen_hashes[digest] = str(path)

        items.append(
            CorpusItem(
                path=str(path),
                filename=path.name,
                title=_title_from_text(clean) or _title_from_filename(path),
                chars=len(clean),
                sha256=digest,
                status=status,
                issue=issue,
                preview=clean[:600],
                duplicate_of=duplicate_of,
            )
        )

    summary = CorpusSummary(
        folder_path=str(folder),
        scanned_at=datetime.now(timezone.utc).isoformat(),
        total_files=len(items),
        usable_files=sum(1 for i in items if i.status == "usable"),
        duplicate_files=sum(1 for i in items if i.status == "duplicate"),
        issue_files=sum(1 for i in items if i.status == "issue"),
        items=items,
    )
    _write_json(CORPUS_MANIFEST, _summary_to_dict(summary))
    return summary


def load_corpus_summary() -> CorpusSummary | None:
    local_dir = ensure_local_uploaded_corpus()
    local_files = [p for p in local_dir.iterdir() if p.is_file() and _is_supported_file(p)]

    if CORPUS_MANIFEST.exists():
        data = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
        items = [CorpusItem(**item) for item in data["items"]]
        # After cloud redeploy, absolute paths in the manifest may be stale.
        if items and any(not Path(item.path).exists() for item in items if item.status == "usable"):
            if local_files:
                return scan_corpus(str(local_dir))
        else:
            return CorpusSummary(
                folder_path=data["folder_path"],
                scanned_at=data["scanned_at"],
                total_files=data["total_files"],
                usable_files=data["usable_files"],
                duplicate_files=data["duplicate_files"],
                issue_files=data["issue_files"],
                items=items,
            )

    if local_files:
        return scan_corpus(str(local_dir))
    return None


def build_dataset(validation_ratio: float = 0.1, seed: int = 42) -> dict:
    summary = load_corpus_summary()
    if not summary:
        raise FileNotFoundError("No corpus scan found. Scan a folder first.")

    usable = [item for item in summary.items if item.status == "usable"]
    if len(usable) < 10:
        raise ValueError("At least 10 usable product-copy files are recommended before export.")

    records = [_dataset_record(item) for item in usable]
    rng = Random(seed)
    rng.shuffle(records)

    validation_count = max(1, int(len(records) * validation_ratio))
    validation = records[:validation_count]
    train = records[validation_count:]

    _write_jsonl(DATASET_JSONL, records)
    _write_jsonl(TRAIN_JSONL, train)
    _write_jsonl(VALIDATION_JSONL, validation)

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_folder": summary.folder_path,
        "total_records": len(records),
        "train_records": len(train),
        "validation_records": len(validation),
        "format": "chatml-jsonl",
        "base_model_recommendation": "Qwen/Qwen2.5-7B-Instruct",
    }
    _write_json(TRAINING_DIR / "dataset-metadata.json", metadata)
    return metadata


def create_training_export() -> Path:
    metadata_path = TRAINING_DIR / "dataset-metadata.json"
    if not TRAIN_JSONL.exists() or not VALIDATION_JSONL.exists() or not metadata_path.exists():
        build_dataset()

    notebook_path = TRAINING_DIR / "train_unsloth_colab.ipynb"
    readme_path = TRAINING_DIR / "README-training.md"
    config_path = TRAINING_DIR / "training-config.json"

    notebook_path.write_text(_training_notebook(), encoding="utf-8")
    readme_path.write_text(_training_readme(), encoding="utf-8")
    _write_json(
        config_path,
        {
            "base_model": "Qwen/Qwen2.5-7B-Instruct",
            "method": "QLoRA",
            "recommended_platforms": ["Kaggle T4", "Google Colab T4", "RunPod RTX 4090"],
            "output_model_name": "my-store-hebrew",
        },
    )

    EXPORT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(EXPORT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in (
            TRAIN_JSONL,
            VALIDATION_JSONL,
            DATASET_JSONL,
            metadata_path,
            config_path,
            notebook_path,
            readme_path,
        ):
            zf.write(path, arcname=path.name)

    if get_settings().storage_backend.lower() == "s3":
        key = "training/product-copy-training-package.zip"
        get_storage().upload_file(EXPORT_ZIP, key)
        EXPORT_STORAGE_KEY.write_text(key, encoding="utf-8")

    return EXPORT_ZIP


def get_training_export_storage_key() -> str | None:
    if EXPORT_STORAGE_KEY.exists():
        return EXPORT_STORAGE_KEY.read_text(encoding="utf-8").strip() or None
    return None


def _is_supported_file(path: Path) -> bool:
    return (
        path.is_file()
        and not path.name.startswith(WORD_TEMP_PREFIX)
        and path.suffix.lower() in BRAND_FILE_EXTENSIONS
        and not path.name.startswith(".")
    )


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title_from_text(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if 4 <= len(stripped) <= 120:
            return stripped
    return ""


def _title_from_filename(path: Path) -> str:
    title = path.stem.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", title).strip()


def _dataset_record(item: CorpusItem) -> dict:
    text = _normalize_text(read_brand_file(Path(item.path)))
    title = item.title or _title_from_filename(Path(item.path))
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write Hebrew e-commerce product copy in the store owner's style. "
                    "This training example teaches style, structure, phrasing, and tone."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"מוצר: {title}\n"
                    "כתוב תיאור מוצר מלא בעברית בסגנון החנות. "
                    "בזמן שימוש אמיתי תקבל מפרטים טכניים בנפרד; כאן המטרה היא ללמוד סגנון כתיבה."
                ),
            },
            {"role": "assistant", "content": text},
        ],
        "metadata": {
            "source_file": item.filename,
            "title": title,
            "chars": item.chars,
            "sha256": item.sha256,
        },
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _summary_to_dict(summary: CorpusSummary) -> dict:
    return {
        "folder_path": summary.folder_path,
        "scanned_at": summary.scanned_at,
        "total_files": summary.total_files,
        "usable_files": summary.usable_files,
        "duplicate_files": summary.duplicate_files,
        "issue_files": summary.issue_files,
        "items": [asdict(item) for item in summary.items],
    }


def _training_readme() -> str:
    return """# Product Copy Training Package

This package contains the dataset created from your existing product-copy Word files.

## Files

- `train.jsonl` - training split
- `validation.jsonl` - validation split
- `dataset.jsonl` - full dataset
- `train_unsloth_colab.ipynb` - starter notebook for Kaggle/Colab
- `training-config.json` - recommended defaults

## Goal

Train a LoRA adapter so the model learns your Hebrew writing style. New product
facts/specs will still come from the manufacturer URL during normal app use.

## Recommended flow

1. Upload this ZIP to Kaggle or Google Colab.
2. Open `train_unsloth_colab.ipynb`.
3. Enable a T4 GPU runtime.
4. Run all cells.
5. Download the trained adapter output.
6. Import/register the trained model in the app in Phase 2.
"""


def _training_notebook() -> str:
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Product Copy Style Fine-Tuning\n",
                    "\n",
                    "Starter notebook for Kaggle/Colab. Uses QLoRA with Unsloth on Qwen 2.5 7B.\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "!pip install -q unsloth trl peft accelerate bitsandbytes datasets transformers\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from datasets import load_dataset\n",
                    "from unsloth import FastLanguageModel\n",
                    "from trl import SFTTrainer\n",
                    "from transformers import TrainingArguments\n",
                    "\n",
                    "BASE_MODEL = 'Qwen/Qwen2.5-7B-Instruct'\n",
                    "MAX_SEQ_LENGTH = 4096\n",
                    "\n",
                    "train_dataset = load_dataset('json', data_files='train.jsonl', split='train')\n",
                    "eval_dataset = load_dataset('json', data_files='validation.jsonl', split='train')\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "model, tokenizer = FastLanguageModel.from_pretrained(\n",
                    "    model_name=BASE_MODEL,\n",
                    "    max_seq_length=MAX_SEQ_LENGTH,\n",
                    "    dtype=None,\n",
                    "    load_in_4bit=True,\n",
                    ")\n",
                    "model = FastLanguageModel.get_peft_model(\n",
                    "    model,\n",
                    "    r=16,\n",
                    "    target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],\n",
                    "    lora_alpha=32,\n",
                    "    lora_dropout=0.05,\n",
                    "    bias='none',\n",
                    "    use_gradient_checkpointing='unsloth',\n",
                    ")\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "def formatting_prompts_func(examples):\n",
                    "    texts = []\n",
                    "    for messages in examples['messages']:\n",
                    "        texts.append(tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False))\n",
                    "    return {'text': texts}\n",
                    "\n",
                    "train_dataset = train_dataset.map(formatting_prompts_func, batched=True)\n",
                    "eval_dataset = eval_dataset.map(formatting_prompts_func, batched=True)\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "trainer = SFTTrainer(\n",
                    "    model=model,\n",
                    "    tokenizer=tokenizer,\n",
                    "    train_dataset=train_dataset,\n",
                    "    eval_dataset=eval_dataset,\n",
                    "    dataset_text_field='text',\n",
                    "    max_seq_length=MAX_SEQ_LENGTH,\n",
                    "    args=TrainingArguments(\n",
                    "        per_device_train_batch_size=1,\n",
                    "        gradient_accumulation_steps=8,\n",
                    "        warmup_steps=10,\n",
                    "        num_train_epochs=3,\n",
                    "        learning_rate=2e-4,\n",
                    "        fp16=True,\n",
                    "        logging_steps=5,\n",
                    "        evaluation_strategy='steps',\n",
                    "        eval_steps=25,\n",
                    "        save_steps=25,\n",
                    "        output_dir='outputs-my-store-hebrew',\n",
                    "        report_to='none',\n",
                    "    ),\n",
                    ")\n",
                    "trainer.train()\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "model.save_pretrained('my-store-hebrew-lora')\n",
                    "tokenizer.save_pretrained('my-store-hebrew-lora')\n",
                    "!zip -r my-store-hebrew-lora.zip my-store-hebrew-lora\n",
                ],
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.x"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, ensure_ascii=False, indent=2)
