import json
import uuid
from datetime import datetime, timezone

import aiosqlite
import asyncpg

from app.config import get_settings
from app.models import JobProgressEvent, JobResponse, JobStatus

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    product_slug TEXT,
    output_path TEXT,
    storage_prefix TEXT,
    progress TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    models_used TEXT NOT NULL DEFAULT '[]',
    variants TEXT NOT NULL DEFAULT '[]',
    config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_estimate INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_queue (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 2,
    run_after TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

POSTGRES_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        url TEXT NOT NULL,
        status TEXT NOT NULL,
        product_slug TEXT,
        output_path TEXT,
        storage_prefix TEXT,
        progress TEXT NOT NULL DEFAULT '[]',
        error TEXT,
        models_used TEXT NOT NULL DEFAULT '[]',
        variants TEXT NOT NULL DEFAULT '[]',
        config TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_usage (
        id SERIAL PRIMARY KEY,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        tokens_estimate INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_queue (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 2,
        run_after TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS storage_prefix TEXT",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_postgres() -> bool:
    return get_settings().using_postgres


async def init_db() -> None:
    settings = get_settings()
    if _is_postgres():
        conn = await asyncpg.connect(settings.database_url)  # type: ignore[arg-type]
        try:
            for statement in POSTGRES_STATEMENTS:
                await conn.execute(statement)
        finally:
            await conn.close()
        return

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.database_path) as db:
        await db.executescript(SQLITE_SCHEMA)
        async with db.execute("PRAGMA table_info(jobs)") as cursor:
            cols = {row[1] for row in await cursor.fetchall()}
        if "storage_prefix" not in cols:
            await db.execute("ALTER TABLE jobs ADD COLUMN storage_prefix TEXT")
        await db.commit()


async def create_job(url: str, config: dict) -> str:
    job_id = str(uuid.uuid4())
    now = _now()
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                """
                INSERT INTO jobs (id, url, status, progress, config, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                job_id,
                url,
                JobStatus.PENDING.value,
                "[]",
                json.dumps(config),
                now,
                now,
            )
        finally:
            await conn.close()
    else:
        async with aiosqlite.connect(get_settings().database_path) as db:
            await db.execute(
                """
                INSERT INTO jobs (id, url, status, progress, config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, url, JobStatus.PENDING.value, "[]", json.dumps(config), now, now),
            )
            await db.commit()
    return job_id


async def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    for key in ("progress", "models_used", "variants", "config"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key])
    if _is_postgres():
        assignments = ", ".join(f"{k} = ${i}" for i, k in enumerate(fields, start=1))
        values = list(fields.values()) + [job_id]
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ${len(values)}",
                *values,
            )
        finally:
            await conn.close()
        return

    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute(f"UPDATE jobs SET {cols} WHERE id = ?", values)
        await db.commit()


async def append_progress(job_id: str, event: JobProgressEvent) -> None:
    job = await get_job(job_id)
    if not job:
        return
    progress = job.progress + [event]
    await update_job(job_id, progress=[e.model_dump() for e in progress])


async def get_job(job_id: str) -> JobResponse | None:
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
        finally:
            await conn.close()
        if not row:
            return None
        return _row_to_job(dict(row))

    async with aiosqlite.connect(get_settings().database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return _row_to_job(row)


async def list_jobs(limit: int = 50) -> list[JobResponse]:
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            rows = await conn.fetch("SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1", limit)
        finally:
            await conn.close()
        return [_row_to_job(dict(r)) for r in rows]

    async with aiosqlite.connect(get_settings().database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_job(r) for r in rows]


def _row_to_job(row: aiosqlite.Row | dict) -> JobResponse:
    progress_raw = json.loads(row["progress"] or "[]")
    progress = [JobProgressEvent(**e) for e in progress_raw]
    return JobResponse(
        id=row["id"],
        url=row["url"],
        status=JobStatus(row["status"]),
        product_slug=row["product_slug"],
        output_path=row["output_path"],
        storage_prefix=row.get("storage_prefix") if isinstance(row, dict) else row["storage_prefix"],
        progress=progress,
        error=row["error"],
        models_used=json.loads(row["models_used"] or "[]"),
        variants=json.loads(row["variants"] or "[]"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


async def record_ai_usage(provider: str, model: str, tokens_estimate: int = 0) -> None:
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                "INSERT INTO ai_usage (provider, model, tokens_estimate, created_at) VALUES ($1, $2, $3, $4)",
                provider,
                model,
                tokens_estimate,
                _now(),
            )
        finally:
            await conn.close()
        return
    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute(
            "INSERT INTO ai_usage (provider, model, tokens_estimate, created_at) VALUES (?, ?, ?, ?)",
            (provider, model, tokens_estimate, _now()),
        )
        await db.commit()


async def get_ai_usage_today() -> dict[str, int]:
    today = datetime.now(timezone.utc).date().isoformat()
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            rows = await conn.fetch(
                """
                SELECT provider, COUNT(*) as cnt
                FROM ai_usage
                WHERE created_at >= $1
                GROUP BY provider
                """,
                today,
            )
        finally:
            await conn.close()
        return {row["provider"]: row["cnt"] for row in rows}

    async with aiosqlite.connect(get_settings().database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT provider, COUNT(*) as cnt
            FROM ai_usage
            WHERE created_at >= ?
            GROUP BY provider
            """,
            (today,),
        ) as cursor:
            rows = await cursor.fetchall()
    return {row["provider"]: row["cnt"] for row in rows}


async def enqueue_job(job_id: str, payload: dict, max_attempts: int | None = None) -> str:
    queue_id = str(uuid.uuid4())
    now = _now()
    attempts_cap = max_attempts or get_settings().worker_max_retries
    payload_json = json.dumps(payload)
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                """
                INSERT INTO job_queue (id, job_id, payload, status, attempts, max_attempts, run_after, created_at, updated_at)
                VALUES ($1, $2, $3, 'pending', 0, $4, $5, $6, $7)
                """,
                queue_id,
                job_id,
                payload_json,
                attempts_cap,
                now,
                now,
                now,
            )
        finally:
            await conn.close()
    else:
        async with aiosqlite.connect(get_settings().database_path) as db:
            await db.execute(
                """
                INSERT INTO job_queue (id, job_id, payload, status, attempts, max_attempts, run_after, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                """,
                (queue_id, job_id, payload_json, attempts_cap, now, now, now),
            )
            await db.commit()
    return queue_id


async def claim_next_queue_job() -> dict | None:
    now = _now()
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            row = await conn.fetchrow(
                """
                WITH next_job AS (
                    SELECT id
                    FROM job_queue
                    WHERE status = 'pending' AND run_after <= $1
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE job_queue q
                SET status = 'running', attempts = attempts + 1, updated_at = $1
                FROM next_job
                WHERE q.id = next_job.id
                RETURNING q.*
                """,
                now,
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async with aiosqlite.connect(get_settings().database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM job_queue
            WHERE status = 'pending' AND run_after <= ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (now,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        await db.execute(
            "UPDATE job_queue SET status = 'running', attempts = attempts + 1, updated_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        await db.commit()
    return dict(row)


async def complete_queue_job(queue_id: str) -> None:
    now = _now()
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute("UPDATE job_queue SET status = 'completed', updated_at = $1 WHERE id = $2", now, queue_id)
        finally:
            await conn.close()
        return
    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute("UPDATE job_queue SET status = 'completed', updated_at = ? WHERE id = ?", (now, queue_id))
        await db.commit()


async def fail_queue_job(queue_id: str, attempts: int, max_attempts: int) -> None:
    now = _now()
    status = "failed" if attempts >= max_attempts else "pending"
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                "UPDATE job_queue SET status = $1, updated_at = $2, run_after = $3 WHERE id = $4",
                status,
                now,
                now,
                queue_id,
            )
        finally:
            await conn.close()
        return
    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute(
            "UPDATE job_queue SET status = ?, updated_at = ?, run_after = ? WHERE id = ?",
            (status, now, now, queue_id),
        )
        await db.commit()


async def queue_stats() -> dict[str, int]:
    out = {"pending": 0, "running": 0, "failed": 0, "completed": 0}
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            rows = await conn.fetch("SELECT status, COUNT(*) AS cnt FROM job_queue GROUP BY status")
        finally:
            await conn.close()
        for row in rows:
            out[row["status"]] = row["cnt"]
        return out
    async with aiosqlite.connect(get_settings().database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status, COUNT(*) AS cnt FROM job_queue GROUP BY status") as cursor:
            rows = await cursor.fetchall()
    for row in rows:
        out[row["status"]] = row["cnt"]
    return out
