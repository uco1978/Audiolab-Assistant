# Operations Runbook

## Health and diagnostics

- API health: `GET /api/health`
- Queue diagnostics: `GET /api/admin/queue`
- UI diagnostics page: `/diagnostics`

## Logging

- API emits structured request logs with:
  - request id
  - method
  - path
  - status
  - latency
- Worker logs each queue claim/success/failure.

## Backup policy

### Postgres

- Enable automated daily backups in hosting provider.
- Keep at least 7-day retention.
- Test restore monthly into a staging database.

### Object storage

- Enable versioning if available.
- Configure lifecycle:
  - keep active generated artifacts indefinitely
  - optionally transition old raw artifacts to colder tier after 30 days
- Restrict public access; serve via signed URLs unless explicit CDN is required.

## Incident response basics

1. Check `/api/health` for database/storage mode.
2. Check `/api/admin/queue` for stuck backlog.
3. Inspect worker logs for repeated failures.
4. Requeue strategy:
   - failed jobs can be reset in DB (`job_queue.status='pending'`) after fix.

## Security checklist

- Rotate `AUTH_JWT_SECRET`, storage keys, and admin password regularly.
- Use strong random secrets (minimum 32 chars).
- Keep `AUTH_ENABLED=true` in production.
- Keep `APP_ENV=production` to disable local-only folder actions.
