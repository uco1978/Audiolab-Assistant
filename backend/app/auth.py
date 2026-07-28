import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.config import get_settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def create_access_token(email: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.auth_token_ttl_hours)
    payload = {
        "sub": email,
        "role": "admin",
        "exp": int(expires.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_b64, settings.auth_jwt_secret)
    return f"{payload_b64}.{signature}", expires


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(401, "Invalid token format") from exc

    expected_sig = _sign(payload_b64, settings.auth_jwt_secret)
    if not hmac.compare_digest(signature, expected_sig):
        raise HTTPException(401, "Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(401, "Invalid token payload") from exc

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if payload.get("exp", 0) < now_ts:
        raise HTTPException(401, "Token expired")
    return payload


def _password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate(email: str, password: str) -> bool:
    settings = get_settings()
    if email.lower().strip() != settings.admin_email.lower().strip():
        return False
    if settings.admin_password_hash:
        return hmac.compare_digest(_password_hash(password), settings.admin_password_hash.strip().lower())
    return hmac.compare_digest(password, settings.admin_password)
