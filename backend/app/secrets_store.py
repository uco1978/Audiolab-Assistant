from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timezone

import aiosqlite
import asyncpg
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

PROVIDER_FIELD_TO_ENV = {
    "gemini_api_key": "GEMINI_API_KEY",
    "groq_api_key": "GROQ_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "cohere_api_key": "COHERE_API_KEY",
    "mistral_api_key": "MISTRAL_API_KEY",
    "perplexity_api_key": "PERPLEXITY_API_KEY",
    "xai_api_key": "XAI_API_KEY",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_postgres() -> bool:
    return get_settings().using_postgres


def _fernet() -> Fernet:
    settings = get_settings()
    material = (settings.secrets_master_key or settings.auth_jwt_secret or "dev-insecure").encode(
        "utf-8"
    )
    digest = hashlib.sha256(b"ppc-secrets-v1:" + material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Failed to decrypt stored API key. Check SECRETS_MASTER_KEY / AUTH_JWT_SECRET."
        ) from exc


async def upsert_secret(name: str, value: str) -> None:
    """Store or replace a secret. Empty value deletes the secret."""
    name = name.strip()
    if not name:
        raise ValueError("Secret name is required")
    if not value.strip():
        await delete_secret(name)
        return

    ciphertext = encrypt_secret(value.strip())
    now = _now()
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                """
                INSERT INTO app_secrets (name, ciphertext, updated_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (name) DO UPDATE
                SET ciphertext = EXCLUDED.ciphertext, updated_at = EXCLUDED.updated_at
                """,
                name,
                ciphertext,
                now,
            )
        finally:
            await conn.close()
        return

    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute(
            """
            INSERT INTO app_secrets (name, ciphertext, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              ciphertext = excluded.ciphertext,
              updated_at = excluded.updated_at
            """,
            (name, ciphertext, now),
        )
        await db.commit()


async def delete_secret(name: str) -> None:
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute("DELETE FROM app_secrets WHERE name = $1", name)
        finally:
            await conn.close()
        return
    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute("DELETE FROM app_secrets WHERE name = ?", (name,))
        await db.commit()


async def get_secret(name: str) -> str | None:
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            row = await conn.fetchrow("SELECT ciphertext FROM app_secrets WHERE name = $1", name)
        finally:
            await conn.close()
        if not row:
            return None
        return decrypt_secret(row["ciphertext"])

    async with aiosqlite.connect(get_settings().database_path) as db:
        async with db.execute("SELECT ciphertext FROM app_secrets WHERE name = ?", (name,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return decrypt_secret(row[0])


async def get_provider_secrets() -> dict[str, str]:
    """Return decrypted provider API keys keyed by settings field name."""
    out: dict[str, str] = {}
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            rows = await conn.fetch("SELECT name, ciphertext FROM app_secrets")
        finally:
            await conn.close()
        for row in rows:
            name = row["name"]
            if name not in PROVIDER_FIELD_TO_ENV:
                continue
            out[name] = decrypt_secret(row["ciphertext"])
        return out

    async with aiosqlite.connect(get_settings().database_path) as db:
        async with db.execute("SELECT name, ciphertext FROM app_secrets") as cursor:
            rows = await cursor.fetchall()
    for name, ciphertext in rows:
        if name not in PROVIDER_FIELD_TO_ENV:
            continue
        out[name] = decrypt_secret(ciphertext)
    return out


async def apply_provider_secrets_to_runtime() -> None:
    """
    Load encrypted provider keys from DB into process env, then refresh settings cache.

    Precedence: DB secret overrides empty env; non-empty Render env vars remain if DB has no value.
    When DB has a value, it wins so Settings UI is source of truth.
    """
    secrets = await get_provider_secrets()
    for field, env_key in PROVIDER_FIELD_TO_ENV.items():
        value = secrets.get(field, "").strip()
        if value:
            os.environ[env_key] = value
        # If DB cleared the secret, do not wipe Render-provided env — leave existing os.environ.
    get_settings.cache_clear()


async def save_provider_keys_from_update(data: dict) -> list[str]:
    """Persist any provider key fields present in an update payload. Returns saved field names."""
    saved: list[str] = []
    for field in PROVIDER_FIELD_TO_ENV:
        if field not in data:
            continue
        raw = data.get(field)
        if raw is None:
            continue
        value = str(raw).strip()
        await upsert_secret(field, value)
        env_key = PROVIDER_FIELD_TO_ENV[field]
        if value:
            os.environ[env_key] = value
        else:
            # Cleared via UI — remove process env so status flips to missing unless Render has it.
            os.environ.pop(env_key, None)
        saved.append(field)
    if saved:
        get_settings.cache_clear()
        await apply_provider_secrets_to_runtime()
    return saved
