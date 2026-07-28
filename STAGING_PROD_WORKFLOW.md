# Staging + Production Workflow

This document keeps ongoing development low-friction after go-live.

## Target model

- Production: stable user-facing environment
- Staging: fast iteration environment for development and testing

Use separate:

- frontend URLs
- backend URLs
- Postgres databases
- object storage buckets (or at least separate prefixes)
- admin/test credentials

## Suggested URLs

- Production frontend: `https://app.yourdomain.com`
- Production API: `https://api.yourdomain.com`
- Staging frontend: `https://staging-app.yourdomain.com`
- Staging API: `https://staging-api.yourdomain.com`

## Branch and deploy strategy

- `main` branch -> production Render services
- `develop` branch -> staging Render services

Do all work through `develop` first. Promote to `main` only after staging validation.

## Render service layout

Create 6 app services + 2 databases:

### Production

- `ppc-backend-prod`
- `ppc-worker-prod`
- `ppc-frontend-prod`
- `ppc-postgres-prod`

### Staging

- `ppc-backend-staging`
- `ppc-worker-staging`
- `ppc-frontend-staging`
- `ppc-postgres-staging`

## Environment files

- production template: `.env.production.example`
- staging template: `.env.staging.example`

Apply template values as Render environment variables (never commit real secrets).

## One-time setup checklist

1. Create R2 buckets:
   - `ppc-assets-prod`
   - `ppc-assets-staging`
2. Create separate Postgres instances (prod/staging).
3. Configure production services to deploy from `main`.
4. Configure staging services to deploy from `develop`.
5. Set frontend `VITE_API_BASE` correctly per environment.
6. Set `TRUSTED_HOSTS` and `CORS_ALLOWED_ORIGINS` correctly per environment.

## Ongoing release flow

1. Implement changes on `develop`.
2. Auto-deploy to staging.
3. Validate staging:
   - login works
   - `/diagnostics` shows healthy queue
   - test job runs from `pending -> running -> completed`
   - output files open
4. Merge `develop` -> `main`.
5. Production auto-deploy.
6. Run production smoke test.

## Standard smoke test (both environments)

1. Open frontend and sign in.
2. Check `GET /api/health`.
3. Check `/diagnostics`.
4. Run one known test product URL.
5. Verify manifest + generated files.

## Minimal-friction collaboration notes

Keep these stable and shared:

- staging frontend URL
- staging API URL
- test account email
- one known test product URL

When requesting follow-up work, include:

- target env (`staging` or `production`)
- failing endpoint or screen URL
- one recent job id if issue is job-related

This enables fast iteration without repeated setup discovery.
