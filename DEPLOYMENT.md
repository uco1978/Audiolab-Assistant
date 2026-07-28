# Cloud Deployment Guide

This app is now cloud-ready and supports:

- managed Postgres via `DATABASE_URL`
- private login via `AUTH_ENABLED=true`
- background worker process (`python -m app.worker`)
- S3-compatible object storage (`STORAGE_BACKEND=s3`)

## 1. Required services

- App hosting: Render/Railway/Fly
- Database: managed Postgres
- Object storage: Cloudflare R2 or AWS S3

## 1.5 Generate strong secrets locally

From `local-edition`:

```powershell
python backend\scripts\generate_secrets.py
```

Use the printed `AUTH_JWT_SECRET` and `ADMIN_PASSWORD_HASH` in production env vars.

## 2. Environment variables

Use `.env.example` as the source of truth. In production set:

- `APP_ENV=production`
- `MODE=cloud`
- `AUTH_ENABLED=true`
- `AUTH_JWT_SECRET=<long-random-secret>`
- `ADMIN_EMAIL=<your-email>`
- `ADMIN_PASSWORD=<strong-password>` (or `ADMIN_PASSWORD_HASH`)
- `DATABASE_URL=<postgres-connection-string>`
- `STORAGE_BACKEND=s3`
- `STORAGE_BUCKET=<bucket>`
- `STORAGE_REGION=<region-or-auto>`
- `STORAGE_ENDPOINT_URL=<r2-or-s3-endpoint>`
- `STORAGE_ACCESS_KEY_ID=<key>`
- `STORAGE_SECRET_ACCESS_KEY=<secret>`

## 3. Deploy with Render blueprint

`render.yaml` defines:

- `ppc-backend` (web API)
- `ppc-worker` (background worker)
- `ppc-frontend` (web UI)
- `ppc-postgres` (database)

Update `VITE_API_BASE` to your backend domain before production cutover.

### Render deployment steps

1. Push this project to GitHub.
2. In Render: **New +** -> **Blueprint** -> connect your repo.
3. Render reads `render.yaml` and creates backend, worker, frontend, postgres.
4. Open each service and set real environment variables:
   - backend + worker: security, database, storage vars
   - frontend: `VITE_API_BASE=https://<your-backend-domain>/api`
5. Redeploy backend, then worker, then frontend.

## 3.5 Cloudflare R2 setup (recommended)

1. Cloudflare dashboard -> R2 -> create bucket (private).
2. Create R2 API token (read+write for this bucket).
3. Copy account endpoint:
   - `https://<accountid>.r2.cloudflarestorage.com`
4. Set backend/worker vars:
   - `STORAGE_BACKEND=s3`
   - `STORAGE_BUCKET=<bucket-name>`
   - `STORAGE_REGION=auto`
   - `STORAGE_ENDPOINT_URL=<endpoint>`
   - `STORAGE_ACCESS_KEY_ID=<access-key>`
   - `STORAGE_SECRET_ACCESS_KEY=<secret-key>`

## 4. Worker requirement

Queue processing runs only in the worker service. If worker is down:

- jobs stay `pending`
- API remains reachable
- no exports are produced

## 5. Domain + TLS

- Attach custom domains in hosting provider dashboard.
- Enforce HTTPS-only access.
- Keep `TRUSTED_HOSTS` aligned with your domain list.

## 6. Go-live smoke test

1. Open frontend URL and sign in.
2. Visit `/diagnostics` and verify queue endpoint returns counts.
3. Create a test job.
4. Confirm:
   - job transitions `pending -> running -> completed`
   - manifest loads
   - file links download via signed URL
5. Check backend `/api/health`:
   - `database` should be `postgres`
   - `storage` should be `s3`

## 7. Post-go-live: staging + prod workflow

After initial launch, set up a two-environment workflow for low-friction iteration:

- use `.env.production.example` for production
- use `.env.staging.example` for staging
- follow [STAGING_PROD_WORKFLOW.md](STAGING_PROD_WORKFLOW.md) for branch/deploy flow
