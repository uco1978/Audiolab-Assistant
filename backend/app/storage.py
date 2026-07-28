from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings

try:
    import boto3
except Exception:  # pragma: no cover - optional dependency for local mode
    boto3 = None


@dataclass
class StoredObject:
    key: str
    url: str | None = None


class StorageBackend:
    def upload_file(self, local_path: Path, key: str) -> StoredObject:
        raise NotImplementedError

    def upload_directory(self, local_dir: Path, prefix: str) -> list[StoredObject]:
        uploaded: list[StoredObject] = []
        for item in local_dir.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(local_dir).as_posix()
            uploaded.append(self.upload_file(item, f"{prefix}/{rel}"))
        return uploaded

    def read_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def signed_url(self, key: str, expires_seconds: int | None = None) -> str:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        safe = key.strip("/").replace("\\", "/")
        full = (self.root / safe).resolve()
        if not str(full).startswith(str(self.root.resolve())):
            raise ValueError("Invalid key path")
        full.parent.mkdir(parents=True, exist_ok=True)
        return full

    def upload_file(self, local_path: Path, key: str) -> StoredObject:
        target = self._path_for(key)
        target.write_bytes(local_path.read_bytes())
        return StoredObject(key=key)

    def read_bytes(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def signed_url(self, key: str, expires_seconds: int | None = None) -> str:
        # local mode streams from API; no direct URL
        return ""


class S3Storage(StorageBackend):
    def __init__(self):
        settings = get_settings()
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 storage backend")
        if not settings.storage_bucket:
            raise RuntimeError("STORAGE_BUCKET is required for S3 storage backend")
        self.bucket = settings.storage_bucket
        self.client = boto3.client(
            "s3",
            region_name=settings.storage_region,
            endpoint_url=settings.storage_endpoint_url,
            aws_access_key_id=settings.storage_access_key_id,
            aws_secret_access_key=settings.storage_secret_access_key,
        )

    def upload_file(self, local_path: Path, key: str) -> StoredObject:
        self.client.upload_file(str(local_path), self.bucket, key)
        return StoredObject(key=key, url=self.signed_url(key))

    def read_bytes(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        body: BinaryIO = obj["Body"]
        return body.read()

    def signed_url(self, key: str, expires_seconds: int | None = None) -> str:
        settings = get_settings()
        if settings.storage_public_base_url:
            return f"{settings.storage_public_base_url.rstrip('/')}/{key}"
        ttl = expires_seconds or settings.storage_signed_url_ttl_seconds
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl,
        )


_storage_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance
    settings = get_settings()
    if settings.storage_backend.lower() == "s3":
        _storage_instance = S3Storage()
    else:
        _storage_instance = LocalStorage(settings.storage_local_dir)
    return _storage_instance
