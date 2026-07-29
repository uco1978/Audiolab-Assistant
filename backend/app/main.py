import json
import logging
import os
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.ai.providers import test_provider_connection
from app.auth import authenticate, create_access_token, decode_access_token
from app.config import PROJECT_ROOT, get_settings
from app.db import (
    create_job,
    enqueue_job,
    get_job,
    init_db,
    list_jobs,
    queue_stats,
)
from app.integrations.woocommerce import sync_product_to_woocommerce
from app.models import (
    AuthUserResponse,
    AiProviderTestRequest,
    CorpusScanRequest,
    CorpusSummaryResponse,
    CreateJobRequest,
    DatasetBuildRequest,
    DatasetBuildResponse,
    JobResponse,
    LoginRequest,
    LoginResponse,
    QueueStatsResponse,
    SettingsUpdate,
    WooCommerceSyncRequest,
)
from app.services.brand_tone import BRAND_FILE_EXTENSIONS
from app.services.training_corpus import (
    build_dataset,
    create_training_export,
    get_training_export_storage_key,
    load_corpus_summary,
    scan_corpus,
)
from app.storage import get_storage

settings = get_settings()
log = logging.getLogger("ppc.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.brand_examples_dir.mkdir(parents=True, exist_ok=True)
    settings.storage_local_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)


@app.middleware("http")
async def request_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.request_max_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    return await call_next(request)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    if not settings.auth_enabled:
        return await call_next(request)
    # Let CORS preflight requests pass without auth.
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if (
        path in {"/api/health", "/api/auth/login", "/api/auth/status"}
        or path.startswith("/docs")
        or path.startswith("/openapi.json")
    ):
        return await call_next(request)
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
        request.state.user = payload
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    log.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "elapsed_ms": elapsed_ms,
            }
        )
    )
    response.headers["x-request-id"] = request_id
    return response


@app.get("/api/health")
async def health():
    db_mode = "postgres" if settings.using_postgres else "sqlite"
    storage_mode = settings.storage_backend
    queue = await queue_stats()
    return {
        "status": "ok",
        "mode": settings.mode,
        "env": settings.app_env,
        "database": db_mode,
        "storage": storage_mode,
        "queue": queue,
    }


@app.get("/api/auth/status")
async def auth_status():
    return {"auth_enabled": settings.auth_enabled}


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if not settings.auth_enabled:
        raise HTTPException(400, "Auth is disabled")
    if not authenticate(body.email, body.password):
        raise HTTPException(401, "Invalid credentials")
    token, expires_at = create_access_token(body.email)
    return LoginResponse(
        access_token=token,
        expires_at=expires_at.isoformat(),
        email=body.email,
    )


@app.get("/api/auth/me", response_model=AuthUserResponse)
async def auth_me(request: Request):
    if not settings.auth_enabled:
        return AuthUserResponse(email="local@offline", role="admin")
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Unauthorized")
    return AuthUserResponse(email=user.get("sub", "unknown"), role=user.get("role", "admin"))


@app.get("/api/ai/status")
async def ai_status():
    s = get_settings()
    providers = {
        "gemini": bool(s.gemini_api_key),
        "groq": bool(s.groq_api_key),
        "openrouter": bool(s.openrouter_api_key),
    }
    configured_models = [m["id"] for m in s.available_models if s.model_is_configured(m["id"])]
    return {
        "ok": len(configured_models) > 0,
        "providers": providers,
        "configured_models": configured_models,
        "fallback_chain": s.model_fallback_chain,
        "default_models": s.default_model_ids,
    }


@app.post("/api/ai/test")
async def ai_test_provider(body: AiProviderTestRequest):
    try:
        result = await test_provider_connection(
            provider=body.provider,
            api_key=body.api_key,
            model_id=body.model_id,
        )
        return result
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "provider": body.provider,
                "error": str(exc),
            },
        )


@app.get("/api/models")
async def list_models():
    s = get_settings()
    return [{**m, "configured": s.model_is_configured(m["id"])} for m in s.available_models]


@app.get("/api/settings")
async def get_settings_endpoint():
    s = get_settings()
    providers = {
        "gemini": bool(s.gemini_api_key),
        "groq": bool(s.groq_api_key),
        "openrouter": bool(s.openrouter_api_key),
    }
    examples = []
    if s.brand_examples_dir.exists():
        examples = [
            p.name
            for p in s.brand_examples_dir.iterdir()
            if p.suffix.lower() in BRAND_FILE_EXTENSIONS and not p.name.startswith("~$")
        ]
    return {
        "mode": settings.mode,
        "app_env": settings.app_env,
        "output_dir": str(s.output_dir),
        "default_models": s.default_models,
        "model_fallback_chain": s.model_fallback_chain,
        "playwright_enabled": s.playwright_enabled,
        "rembg_enabled": s.rembg_enabled,
        "webp_quality": s.webp_quality,
        "brand_examples_dir": str(s.brand_examples_dir),
        "brand_examples": examples,
        "auth_enabled": s.auth_enabled,
        "storage_backend": s.storage_backend,
        "providers": providers,
    }


@app.get("/api/training/corpus", response_model=CorpusSummaryResponse | None)
async def get_training_corpus():
    return load_corpus_summary()


@app.post("/api/training/corpus/scan", response_model=CorpusSummaryResponse)
async def scan_training_corpus(body: CorpusScanRequest):
    try:
        return scan_corpus(body.folder_path)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/training/dataset", response_model=DatasetBuildResponse)
async def build_training_dataset(body: DatasetBuildRequest):
    try:
        return build_dataset(validation_ratio=body.validation_ratio, seed=body.seed)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/training/export")
async def export_training_package():
    try:
        path = create_training_export()
        payload = {"path": str(path), "filename": path.name}
        if settings.storage_backend.lower() == "s3":
            key = get_training_export_storage_key()
            if key:
                payload["url"] = get_storage().signed_url(key)
        return payload
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/training/export/download")
async def download_training_package():
    try:
        path = create_training_export()
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    if settings.storage_backend.lower() == "s3":
        key = get_training_export_storage_key()
        if key:
            return RedirectResponse(get_storage().signed_url(key))
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
    )


@app.put("/api/settings")
async def update_settings(body: SettingsUpdate):
    env_path = PROJECT_ROOT / ".env"
    lines: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                lines[k.strip()] = v.strip()

    mapping = {
        "gemini_api_key": "GEMINI_API_KEY",
        "groq_api_key": "GROQ_API_KEY",
        "openrouter_api_key": "OPENROUTER_API_KEY",
        "default_models": "DEFAULT_MODELS",
        "model_fallback_chain": "MODEL_FALLBACK_CHAIN",
        "output_dir": "OUTPUT_DIR",
        "playwright_enabled": "PLAYWRIGHT_ENABLED",
        "rembg_enabled": "REMBG_ENABLED",
        "webp_quality": "WEBP_QUALITY",
        "brand_examples_dir": "BRAND_EXAMPLES_DIR",
    }
    data = body.model_dump(exclude_none=True)
    for field, env_key in mapping.items():
        if field in data:
            val = data[field]
            lines[env_key] = str(val).lower() if isinstance(val, bool) else str(val)

    env_path.write_text("\n".join(f"{k}={v}" for k, v in lines.items()) + "\n", encoding="utf-8")
    get_settings.cache_clear()
    return await get_settings_endpoint()


@app.post("/api/jobs", response_model=JobResponse)
async def create_job_endpoint(body: CreateJobRequest):
    config = {
        "web_search": body.web_search,
        "use_playwright": body.use_playwright,
        "rembg_enabled": body.rembg_enabled,
        "ai_image_selection": body.ai_image_selection,
    }
    job_id = await create_job(str(body.url), config)
    await enqueue_job(job_id, {"url": str(body.url), "config": config}, max_attempts=settings.worker_max_retries)
    return await get_job(job_id)


@app.get("/api/jobs", response_model=list[JobResponse])
async def list_jobs_endpoint():
    return await list_jobs()


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_endpoint(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs/{job_id}/open-folder")
async def open_folder(job_id: str):
    if settings.app_env != "development":
        raise HTTPException(403, "Open folder is available only in development mode")
    job = await get_job(job_id)
    if not job or not job.output_path:
        raise HTTPException(404, "Job or output not found")
    if os.name == "nt":
        subprocess.Popen(["explorer", str(job.output_path)])  # noqa: S603
    return {"path": job.output_path}


@app.get("/api/jobs/{job_id}/manifest")
async def get_job_manifest(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.storage_prefix:
        data = get_storage().read_bytes(f"{job.storage_prefix}/manifest.json")
        return json.loads(data.decode("utf-8"))
    if not job.output_path:
        raise HTTPException(404, "Manifest not found")
    manifest_path = Path(job.output_path) / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, "Manifest not found")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@app.get("/api/jobs/{job_id}/files/{file_path:path}")
async def get_job_file(job_id: str, file_path: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.storage_prefix:
        key = f"{job.storage_prefix}/{file_path.strip('/')}"
        if settings.storage_backend.lower() == "s3":
            return RedirectResponse(get_storage().signed_url(key))
        data = get_storage().read_bytes(key)
        return FileResponse(Path((settings.storage_local_dir / key).resolve()))
    if not job.output_path:
        raise HTTPException(404, "Job not found")
    full = (Path(job.output_path) / file_path).resolve()
    base = Path(job.output_path).resolve()
    if not str(full).startswith(str(base)):
        raise HTTPException(403, "Invalid path")
    if not full.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(full)


@app.post("/api/jobs/{job_id}/sync-woocommerce")
async def sync_woocommerce(job_id: str, body: WooCommerceSyncRequest):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job or output not found")
    if job.storage_prefix:
        raise HTTPException(400, "WooCommerce sync currently requires local output path")
    if not job.output_path:
        raise HTTPException(404, "Job or output not found")
    try:
        result = await sync_product_to_woocommerce(
            Path(job.output_path),
            body.site_url,
            body.consumer_key,
            body.consumer_secret,
            category_id=body.category_id,
            status=body.status,
        )
        return {"ok": True, "product": result}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/admin/queue", response_model=QueueStatsResponse)
async def queue_diagnostics():
    stats = await queue_stats()
    return QueueStatsResponse(**stats)
