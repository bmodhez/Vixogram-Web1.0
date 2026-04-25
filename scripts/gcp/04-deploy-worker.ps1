param(
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [Parameter(Mandatory=$true)][string]$Region,
    [Parameter(Mandatory=$true)][string]$RepoName,
    [Parameter(Mandatory=$true)][string]$WorkerServiceName,
    [Parameter(Mandatory=$true)][string]$Tag,
    [Parameter(Mandatory=$true)][string]$CloudSqlConnectionName
)

$ErrorActionPreference = 'Stop'

$Image = "$Region-docker.pkg.dev/$ProjectId/$RepoName/vixogram-web:$Tag"

gcloud config set project $ProjectId

Write-Host "Deploying Celery worker on Cloud Run (always-on min instance)..."
gcloud run deploy $WorkerServiceName --image $Image --region $Region --platform managed --no-allow-unauthenticated --min-instances 1 --max-instances 1 --cpu 1 --memory 1Gi --no-cpu-throttling --set-env-vars "ENVIRONMENT=production,DEBUG=0" --set-secrets "SECRET_KEY=SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest" --add-cloudsql-instances $CloudSqlConnectionName --command celery --args "-A,a_core,worker,--loglevel=INFO,--concurrency=2"

Write-Host "Worker deploy complete."
