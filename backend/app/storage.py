from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass
class StorageObjectInfo:
    key: str
    size: int
    last_modified: str | None = None


@dataclass
class StorageListing:
    prefix: str
    folders: list[str]
    objects: list[StorageObjectInfo]
    total_bytes: int


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

    def list_prefix(self, prefix: str = "") -> StorageListing:
        raise NotImplementedError

    def delete_keys(self, keys: list[str]) -> int:
        raise NotImplementedError

    def delete_prefix(self, prefix: str) -> int:
        raise NotImplementedError


def _normalize_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class LocalStorage(StorageBackend):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str, *, create_parent: bool = True) -> Path:
        safe = key.strip("/").replace("\\", "/")
        full = (self.root / safe).resolve()
        if not str(full).startswith(str(self.root.resolve())):
            raise ValueError("Invalid key path")
        if create_parent:
            full.parent.mkdir(parents=True, exist_ok=True)
        return full

    def upload_file(self, local_path: Path, key: str) -> StoredObject:
        target = self._path_for(key)
        target.write_bytes(local_path.read_bytes())
        return StoredObject(key=key)

    def read_bytes(self, key: str) -> bytes:
        return self._path_for(key, create_parent=False).read_bytes()

    def signed_url(self, key: str, expires_seconds: int | None = None) -> str:
        return ""

    def list_prefix(self, prefix: str = "") -> StorageListing:
        norm = _normalize_prefix(prefix)
        base = self.root / norm if norm else self.root
        base = base.resolve()
        if not str(base).startswith(str(self.root.resolve())):
            raise ValueError("Invalid prefix")
        if not base.exists():
            return StorageListing(prefix=norm, folders=[], objects=[], total_bytes=0)

        folders: list[str] = []
        objects: list[StorageObjectInfo] = []
        total = 0
        if base.is_dir():
            for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
                rel = child.relative_to(self.root).as_posix()
                if child.is_dir():
                    folders.append(rel.rstrip("/") + "/")
                elif child.is_file():
                    size = child.stat().st_size
                    total += size
                    objects.append(
                        StorageObjectInfo(
                            key=rel,
                            size=size,
                            last_modified=_iso(datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)),
                        )
                    )
        return StorageListing(prefix=norm, folders=folders, objects=objects, total_bytes=total)

    def delete_keys(self, keys: list[str]) -> int:
        deleted = 0
        for key in keys:
            path = self._path_for(key, create_parent=False)
            if path.is_file():
                path.unlink()
                deleted += 1
                # Clean empty parents up to storage root
                parent = path.parent
                while parent != self.root.resolve() and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
        return deleted

    def delete_prefix(self, prefix: str) -> int:
        norm = _normalize_prefix(prefix)
        if not norm:
            raise ValueError("Refusing to delete entire storage root")
        base = self._path_for(norm, create_parent=False)
        if not base.exists():
            return 0
        deleted = 0
        if base.is_file():
            base.unlink()
            return 1
        for item in sorted(base.rglob("*"), reverse=True):
            if item.is_file():
                item.unlink()
                deleted += 1
            elif item.is_dir():
                item.rmdir()
        if base.exists() and base.is_dir():
            base.rmdir()
        return deleted


class S3Storage(StorageBackend):
    def __init__(self):
        settings = get_settings()
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 storage backend")
        if not settings.storage_bucket:
            raise RuntimeError("STORAGE_BUCKET is required for S3 storage backend")
        from botocore.config import Config

        access_key = (settings.storage_access_key_id or "").strip()
        secret_key = (settings.storage_secret_access_key or "").strip()
        endpoint = (settings.storage_endpoint_url or "").strip() or None
        region = (settings.storage_region or "auto").strip() or "auto"
        if not access_key or not secret_key:
            raise RuntimeError("STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY are required")

        self.bucket = settings.storage_bucket.strip()
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def upload_file(self, local_path: Path, key: str) -> StoredObject:
        try:
            self.client.upload_file(str(local_path), self.bucket, key)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to upload {local_path.as_posix()} to {self.bucket}/{key}: {exc}"
            ) from exc
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

    def list_prefix(self, prefix: str = "") -> StorageListing:
        norm = _normalize_prefix(prefix)
        list_prefix = f"{norm}/" if norm else ""
        folders: list[str] = []
        objects: list[StorageObjectInfo] = []
        total = 0
        token: str | None = None
        while True:
            kwargs: dict = {
                "Bucket": self.bucket,
                "Prefix": list_prefix,
                "Delimiter": "/",
            }
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            for cp in resp.get("CommonPrefixes") or []:
                p = cp.get("Prefix") or ""
                if p:
                    folders.append(p)
            for obj in resp.get("Contents") or []:
                key = obj.get("Key") or ""
                if not key or key.endswith("/"):
                    continue
                # Skip the "folder placeholder" that equals the prefix itself
                if key.rstrip("/") == norm:
                    continue
                size = int(obj.get("Size") or 0)
                total += size
                objects.append(
                    StorageObjectInfo(
                        key=key,
                        size=size,
                        last_modified=_iso(obj.get("LastModified")),
                    )
                )
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        folders.sort()
        objects.sort(key=lambda o: o.key.lower())
        return StorageListing(prefix=norm, folders=folders, objects=objects, total_bytes=total)

    def delete_keys(self, keys: list[str]) -> int:
        clean = [k.strip().lstrip("/") for k in keys if k and k.strip()]
        if not clean:
            return 0
        deleted = 0
        for i in range(0, len(clean), 1000):
            batch = clean[i : i + 1000]
            resp = self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
            errors = resp.get("Errors") or []
            deleted += len(batch) - len(errors)
            if errors:
                first = errors[0]
                raise RuntimeError(
                    f"Failed to delete {first.get('Key')}: {first.get('Message', 'unknown error')}"
                )
        return deleted

    def delete_prefix(self, prefix: str) -> int:
        norm = _normalize_prefix(prefix)
        if not norm:
            raise ValueError("Refusing to delete entire bucket")
        list_prefix = f"{norm}/"
        deleted = 0
        token: str | None = None
        while True:
            kwargs: dict = {"Bucket": self.bucket, "Prefix": list_prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            keys = [obj["Key"] for obj in (resp.get("Contents") or []) if obj.get("Key")]
            if keys:
                deleted += self.delete_keys(keys)
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return deleted


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
