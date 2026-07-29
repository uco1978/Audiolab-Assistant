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
    user_rating INTEGER,
    timing TEXT NOT NULL DEFAULT '{}',
    fallback_models TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_estimate INTEGER DEFAULT 0,
    outcome TEXT NOT NULL DEFAULT 'success',
    error_class TEXT,
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
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
        user_rating INTEGER,
        timing TEXT NOT NULL DEFAULT '{}',
        fallback_models TEXT NOT NULL DEFAULT '[]',
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
        outcome TEXT NOT NULL DEFAULT 'success',
        error_class TEXT,
        latency_ms INTEGER,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
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
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_rating INTEGER",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS timing TEXT NOT NULL DEFAULT '{}'",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fallback_models TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE ai_usage ADD COLUMN IF NOT EXISTS outcome TEXT NOT NULL DEFAULT 'success'",
    "ALTER TABLE ai_usage ADD COLUMN IF NOT EXISTS error_class TEXT",
    "ALTER TABLE ai_usage ADD COLUMN IF NOT EXISTS latency_ms INTEGER",
    "ALTER TABLE ai_usage ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER",
    "ALTER TABLE ai_usage ADD COLUMN IF NOT EXISTS completion_tokens INTEGER",
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
        if "user_rating" not in cols:
            await db.execute("ALTER TABLE jobs ADD COLUMN user_rating INTEGER")
        if "timing" not in cols:
            await db.execute("ALTER TABLE jobs ADD COLUMN timing TEXT NOT NULL DEFAULT '{}'")
        if "fallback_models" not in cols:
            await db.execute("ALTER TABLE jobs ADD COLUMN fallback_models TEXT NOT NULL DEFAULT '[]'")
        async with db.execute("PRAGMA table_info(ai_usage)") as cursor:
            ai_cols = {row[1] for row in await cursor.fetchall()}
        if "outcome" not in ai_cols:
            await db.execute("ALTER TABLE ai_usage ADD COLUMN outcome TEXT NOT NULL DEFAULT 'success'")
        if "error_class" not in ai_cols:
            await db.execute("ALTER TABLE ai_usage ADD COLUMN error_class TEXT")
        if "latency_ms" not in ai_cols:
            await db.execute("ALTER TABLE ai_usage ADD COLUMN latency_ms INTEGER")
        if "prompt_tokens" not in ai_cols:
            await db.execute("ALTER TABLE ai_usage ADD COLUMN prompt_tokens INTEGER")
        if "completion_tokens" not in ai_cols:
            await db.execute("ALTER TABLE ai_usage ADD COLUMN completion_tokens INTEGER")
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
    for key in ("progress", "models_used", "variants", "config", "timing", "fallback_models"):
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
        user_rating=row.get("user_rating") if isinstance(row, dict) else (row["user_rating"] if "user_rating" in row.keys() else None),
        progress=progress,
        error=row["error"],
        models_used=json.loads(row["models_used"] or "[]"),
        variants=json.loads(row["variants"] or "[]"),
        timing=json.loads(row.get("timing", "{}") if isinstance(row, dict) else (row["timing"] if "timing" in row.keys() else "{}")),
        fallback_models=json.loads(row.get("fallback_models", "[]") if isinstance(row, dict) else (row["fallback_models"] if "fallback_models" in row.keys() else "[]")),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


async def record_ai_usage(
    provider: str,
    model: str,
    tokens_estimate: int = 0,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    now = _now()
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                """INSERT INTO ai_usage
                   (provider, model, tokens_estimate, outcome, latency_ms, prompt_tokens, completion_tokens, created_at)
                   VALUES ($1,$2,$3,'success',$4,$5,$6,$7)""",
                provider, model, tokens_estimate, latency_ms, prompt_tokens, completion_tokens, now,
            )
        finally:
            await conn.close()
        return
    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute(
            """INSERT INTO ai_usage
               (provider, model, tokens_estimate, outcome, latency_ms, prompt_tokens, completion_tokens, created_at)
               VALUES (?,?,?,'success',?,?,?,?)""",
            (provider, model, tokens_estimate, latency_ms, prompt_tokens, completion_tokens, now),
        )
        await db.commit()


async def record_ai_failure(
    provider: str, model: str, latency_ms: int, error_class: str,
) -> None:
    now = _now()
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            await conn.execute(
                """INSERT INTO ai_usage
                   (provider, model, tokens_estimate, outcome, error_class, latency_ms, created_at)
                   VALUES ($1,$2,0,'failure',$3,$4,$5)""",
                provider, model, error_class, latency_ms, now,
            )
        finally:
            await conn.close()
        return
    async with aiosqlite.connect(get_settings().database_path) as db:
        await db.execute(
            """INSERT INTO ai_usage
               (provider, model, tokens_estimate, outcome, error_class, latency_ms, created_at)
               VALUES (?,?,0,'failure',?,?,?)""",
            (provider, model, error_class, latency_ms, now),
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


async def get_ai_usage_summary() -> dict:
    from datetime import timedelta

    now_dt = datetime.now(timezone.utc)
    cutoff_24h = (now_dt - timedelta(hours=24)).isoformat()
    cutoff_7d = (now_dt - timedelta(days=7)).isoformat()

    query = """
        SELECT provider, model, outcome, COUNT(*) as cnt,
               COALESCE(AVG(latency_ms),0) as avg_lat,
               COALESCE(SUM(tokens_estimate),0) as total_tok
        FROM ai_usage WHERE created_at >= {cutoff}
        GROUP BY provider, model, outcome
    """

    async def _run(cutoff: str) -> dict:
        if _is_postgres():
            sql = query.replace("{cutoff}", "$1")
            conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
            try:
                rows = [dict(r) for r in await conn.fetch(sql, cutoff)]
            finally:
                await conn.close()
        else:
            sql = query.replace("{cutoff}", "?")
            async with aiosqlite.connect(get_settings().database_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(sql, (cutoff,)) as cursor:
                    rows = [dict(r) for r in await cursor.fetchall()]

        by_provider: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        total_calls = 0
        total_failures = 0
        for r in rows:
            cnt = r["cnt"]
            total_calls += cnt
            if r["outcome"] != "success":
                total_failures += cnt
            prov = r["provider"]
            if prov not in by_provider:
                by_provider[prov] = {"provider": prov, "calls": 0, "failures": 0, "avg_latency_ms": 0, "total_tokens": 0, "_lat_sum": 0}
            by_provider[prov]["calls"] += cnt
            if r["outcome"] != "success":
                by_provider[prov]["failures"] += cnt
            by_provider[prov]["total_tokens"] += int(r["total_tok"])
            by_provider[prov]["_lat_sum"] += float(r["avg_lat"]) * cnt

            mid = r["model"]
            if mid not in by_model:
                by_model[mid] = {"model": mid, "calls": 0, "failures": 0, "avg_latency_ms": 0, "total_tokens": 0, "_lat_sum": 0}
            by_model[mid]["calls"] += cnt
            if r["outcome"] != "success":
                by_model[mid]["failures"] += cnt
            by_model[mid]["total_tokens"] += int(r["total_tok"])
            by_model[mid]["_lat_sum"] += float(r["avg_lat"]) * cnt

        for d in list(by_provider.values()) + list(by_model.values()):
            d["avg_latency_ms"] = round(d.pop("_lat_sum") / d["calls"]) if d["calls"] else 0

        return {
            "by_provider": list(by_provider.values()),
            "by_model": list(by_model.values()),
            "total_calls": total_calls,
            "total_failures": total_failures,
        }

    return {
        "last_24h": await _run(cutoff_24h),
        "last_7d": await _run(cutoff_7d),
    }


async def get_recent_errors(limit: int = 20) -> list[dict]:
    sql_base = """
        SELECT provider, model, error_class, created_at
        FROM ai_usage WHERE outcome != 'success' AND error_class IS NOT NULL
        ORDER BY created_at DESC LIMIT {limit}
    """
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            rows = await conn.fetch(sql_base.replace("{limit}", "$1"), limit)
        finally:
            await conn.close()
        return [dict(r) for r in rows]
    async with aiosqlite.connect(get_settings().database_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql_base.replace("{limit}", "?"), (limit,)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_model_ratings_summary() -> list[dict]:
    sql = """
        SELECT models_used, user_rating FROM jobs
        WHERE status = 'completed' AND user_rating IS NOT NULL
    """
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            rows = [dict(r) for r in await conn.fetch(sql)]
        finally:
            await conn.close()
    else:
        async with aiosqlite.connect(get_settings().database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql) as cursor:
                rows = [dict(r) for r in await cursor.fetchall()]

    agg: dict[str, list[int]] = {}
    for r in rows:
        models = json.loads(r["models_used"] or "[]")
        rating = r["user_rating"]
        for m in models:
            agg.setdefault(m, []).append(rating)

    return [
        {
            "model": m,
            "avg_rating": round(sum(ratings) / len(ratings), 2),
            "rated_jobs": len(ratings),
        }
        for m, ratings in agg.items()
    ]


async def get_recent_jobs_diagnostics(limit: int = 10) -> list[dict]:
    sql_base = """
        SELECT id, url, status, models_used, user_rating, timing, fallback_models, created_at
        FROM jobs ORDER BY created_at DESC LIMIT {limit}
    """
    if _is_postgres():
        conn = await asyncpg.connect(get_settings().database_url)  # type: ignore[arg-type]
        try:
            rows = [dict(r) for r in await conn.fetch(sql_base.replace("{limit}", "$1"), limit)]
        finally:
            await conn.close()
    else:
        async with aiosqlite.connect(get_settings().database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql_base.replace("{limit}", "?"), (limit,)) as cursor:
                rows = [dict(r) for r in await cursor.fetchall()]

    for r in rows:
        r["models_used"] = json.loads(r.get("models_used") or "[]")
        r["timing"] = json.loads(r.get("timing") or "{}")
        r["fallback_models"] = json.loads(r.get("fallback_models") or "[]")
    return rows
