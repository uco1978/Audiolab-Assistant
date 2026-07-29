from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStep(str, Enum):
    VALIDATE = "validate"
    SCRAPE = "scrape"
    SEARCH = "search"
    DOWNLOAD_IMAGES = "download_images"
    PROCESS_IMAGES = "process_images"
    GENERATE_COPY = "generate_copy"
    EXPORT = "export"
    DONE = "done"


class CreateJobRequest(BaseModel):
    url: HttpUrl
    web_search: bool = False
    use_playwright: bool = False
    rembg_enabled: bool | None = None
    ai_image_selection: bool = True


class JobProgressEvent(BaseModel):
    step: JobStep
    message: str
    percent: int = 0
    detail: dict[str, Any] | None = None


class JobResponse(BaseModel):
    id: str
    url: str
    status: JobStatus
    product_slug: str | None = None
    output_path: str | None = None
    storage_prefix: str | None = None
    progress: list[JobProgressEvent] = Field(default_factory=list)
    error: str | None = None
    models_used: list[str] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SettingsUpdate(BaseModel):
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None
    default_models: str | None = None
    model_fallback_chain: str | None = None
    output_dir: str | None = None
    brand_examples_dir: str | None = None
    playwright_enabled: bool | None = None
    rembg_enabled: bool | None = None
    webp_quality: int | None = None


class WooCommerceSyncRequest(BaseModel):
    site_url: str
    consumer_key: str
    consumer_secret: str
    category_id: int | None = None
    status: str = "draft"


class CorpusScanRequest(BaseModel):
    folder_path: str


class CorpusItemResponse(BaseModel):
    path: str
    filename: str
    title: str
    chars: int
    sha256: str
    status: str
    issue: str | None = None
    preview: str = ""
    duplicate_of: str | None = None


class CorpusSummaryResponse(BaseModel):
    folder_path: str
    scanned_at: str
    total_files: int
    usable_files: int
    duplicate_files: int
    issue_files: int
    items: list[CorpusItemResponse] = Field(default_factory=list)


class DatasetBuildRequest(BaseModel):
    validation_ratio: float = 0.1
    seed: int = 42


class DatasetBuildResponse(BaseModel):
    created_at: str
    source_folder: str
    total_records: int
    train_records: int
    validation_records: int
    format: str
    base_model_recommendation: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    email: str


class AuthUserResponse(BaseModel):
    email: str
    role: str = "admin"


class QueueStatsResponse(BaseModel):
    pending: int
    running: int
    failed: int
    completed: int
