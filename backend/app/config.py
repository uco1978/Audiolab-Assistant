from pathlib import Path
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: str = "local"
    app_env: str = "development"
    app_name: str = "Product Page Creator"
    app_version: str = "2.0.0"
    ollama_base_url: str = "http://localhost:11434"
    frontend_url: str = "http://localhost:5174"
    cors_allowed_origins: str = "http://localhost:5174,http://127.0.0.1:5174,http://localhost:5173,http://127.0.0.1:5173"
    trusted_hosts: str = "localhost,127.0.0.1"
    request_max_mb: int = 30

    text_model: str = "qwen2.5:7b-instruct"
    vision_model: str = "qwen2.5vl:7b"

    enable_cloud_fallback: bool = False
    brand_examples_dir: Path = PROJECT_ROOT / "brand-examples"
    max_brand_examples: int = 3

    output_dir: Path = Path.home() / "product-assets"
    playwright_enabled: bool = True
    rembg_enabled: bool = True
    webp_quality: int = 90
    ai_image_selection: bool = True

    database_path: Path = PROJECT_ROOT / "data" / "jobs.db"
    database_url: str | None = None
    storage_backend: str = "local"
    storage_local_dir: Path = PROJECT_ROOT / "data" / "storage"
    storage_bucket: str = ""
    storage_region: str = "auto"
    storage_endpoint_url: str | None = None
    storage_access_key_id: str | None = None
    storage_secret_access_key: str | None = None
    storage_public_base_url: str | None = None
    storage_signed_url_ttl_seconds: int = 900

    auth_enabled: bool = False
    auth_jwt_secret: str = "change-me-in-production"
    auth_token_ttl_hours: int = 24
    admin_email: str = "admin@example.com"
    admin_password: str = "changeme"
    admin_password_hash: str | None = None

    worker_poll_seconds: int = 5
    worker_max_retries: int = 2

    @field_validator("brand_examples_dir", mode="before")
    @classmethod
    def resolve_brand_dir(cls, v: str | Path | None) -> Path:
        if v is None:
            return PROJECT_ROOT / "brand-examples"
        p = Path(v)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @field_validator("output_dir", mode="before")
    @classmethod
    def resolve_output_dir(cls, v: str | Path | None) -> Path:
        if v is None:
            return Path.home() / "product-assets"
        return Path(v)

    @field_validator("storage_local_dir", mode="before")
    @classmethod
    def resolve_storage_dir(cls, v: str | Path | None) -> Path:
        if v is None:
            return PROJECT_ROOT / "data" / "storage"
        p = Path(v)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def text_model_litellm(self) -> str:
        return f"ollama/{self.text_model}"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]

    @property
    def using_postgres(self) -> bool:
        return bool(self.database_url and self.database_url.startswith("postgres"))

    @property
    def request_max_bytes(self) -> int:
        return self.request_max_mb * 1024 * 1024

    @property
    def available_models(self) -> list[dict]:
        return [
            {
                "id": self.text_model_litellm,
                "label": f"Text: {self.text_model}",
                "provider": "ollama",
                "role": "text",
            },
            {
                "id": f"ollama/{self.vision_model}",
                "label": f"Vision: {self.vision_model}",
                "provider": "ollama",
                "role": "vision",
            },
        ]

    def model_is_configured(self, model_id: str) -> bool:
        return model_id.startswith("ollama/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
