# GCP Deployment Guide (Vixogram)

This guide deploys Vixogram to Google Cloud Run with Cloud SQL PostgreSQL and optional Celery worker.

## 1) Required APIs

Run:

```powershell
./scripts/gcp/01-enable-apis.ps1 -ProjectId "YOUR_PROJECT_ID"
```

Enabled APIs:
- Cloud Run
- Cloud Build
- Artifact Registry
- Cloud SQL Admin
- Secret Manager
- Service Networking

## 2) Billing Budget Alerts (25/50/75/90)

Create in Console:
- Billing > Budgets & alerts > Create budget
- Threshold rules: 25%, 50%, 75%, 90%
- Enable email alerts

## 3) Create Cloud SQL PostgreSQL

```powershell
./scripts/gcp/02-create-cloudsql.ps1 -ProjectId "YOUR_PROJECT_ID" -Region "asia-south1" -InstanceName "vixogram-pg" -DbName "vixogram" -DbUser "vixo_user" -DbPassword "CHANGE_ME_STRONG"
```

## 4) Secret Manager values

Create these secrets in GCP Secret Manager:
- SECRET_KEY
- DATABASE_URL
- REDIS_URL

`DATABASE_URL` format:

```text
postgresql://DB_USER:DB_PASSWORD@/DB_NAME?host=/cloudsql/CLOUDSQL_CONNECTION_NAME
```

Example:

```text
postgresql://vixo_user:CHANGE_ME_STRONG@/vixogram?host=/cloudsql/my-project:asia-south1:vixogram-pg
```

## 5) Deploy Web (ASGI + Daphne)

```powershell
./scripts/gcp/03-deploy-web.ps1 -ProjectId "YOUR_PROJECT_ID" -Region "asia-south1" -RepoName "vixogram" -ServiceName "vixogram-web" -Tag "v1" -CloudSqlConnectionName "YOUR_PROJECT_ID:asia-south1:vixogram-pg"
```

## 6) Run Migrations via Cloud Run Job

```powershell
./scripts/gcp/05-run-migrate-job.ps1 -ProjectId "YOUR_PROJECT_ID" -Region "asia-south1" -RepoName "vixogram" -JobName "vixogram-migrate" -Tag "v1" -CloudSqlConnectionName "YOUR_PROJECT_ID:asia-south1:vixogram-pg"
```

## 7) Deploy Celery Worker (optional but recommended)

```powershell
./scripts/gcp/04-deploy-worker.ps1 -ProjectId "YOUR_PROJECT_ID" -Region "asia-south1" -RepoName "vixogram" -WorkerServiceName "vixogram-worker" -Tag "v1" -CloudSqlConnectionName "YOUR_PROJECT_ID:asia-south1:vixogram-pg"
```

## 8) Domain Mapping (vixogram.tech)

Map domain to Cloud Run service in Console:
- Cloud Run > vixogram-web > Manage custom domains
- Add:
  - vixogram.tech
  - www.vixogram.tech

Then add DNS records at your domain registrar exactly as shown by Google Cloud.

SSL certificates are auto-provisioned by Google after DNS propagation.

## 9) Security env defaults already in code

Project settings include:
- ALLOWED_HOSTS includes vixogram.tech and www.vixogram.tech
- CSRF_TRUSTED_ORIGINS includes https://vixogram.tech and https://www.vixogram.tech
- secure cookies enabled in production
- SSL redirect enabled by default in production

## 10) Cost controls

- Cloud Run web min instances: 0 (cold starts, cheaper)
- Cloud Run worker min instances: 1 (only if Celery needed)
- Cloud SQL: smallest shared-core start
- Budget alerts at 25/50/75/90

## Notes

- Rotate all leaked credentials before production cutover.
- Keep DEBUG=0 and ENVIRONMENT=production.
- Verify Redis URL supports TLS (`rediss://`) if using hosted Redis.
