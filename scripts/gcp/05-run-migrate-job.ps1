param(
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [Parameter(Mandatory=$true)][string]$Region,
    [Parameter(Mandatory=$true)][string]$RepoName,
    [Parameter(Mandatory=$true)][string]$JobName,
    [Parameter(Mandatory=$true)][string]$Tag,
    [Parameter(Mandatory=$true)][string]$CloudSqlConnectionName
)

$ErrorActionPreference = 'Stop'

$Image = "$Region-docker.pkg.dev/$ProjectId/$RepoName/vixogram-web:$Tag"

gcloud config set project $ProjectId

Write-Host "Creating/updating Cloud Run migration job..."
try {
    gcloud run jobs describe $JobName --region $Region | Out-Null
    gcloud run jobs update $JobName --region $Region --image $Image --set-env-vars "ENVIRONMENT=production,DEBUG=0" --set-secrets "SECRET_KEY=SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest" --add-cloudsql-instances $CloudSqlConnectionName --command python --args "manage.py,migrate,--noinput"
} catch {
    gcloud run jobs create $JobName --region $Region --image $Image --set-env-vars "ENVIRONMENT=production,DEBUG=0" --set-secrets "SECRET_KEY=SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest" --add-cloudsql-instances $CloudSqlConnectionName --command python --args "manage.py,migrate,--noinput"
}

Write-Host "Executing migration job..."
gcloud run jobs execute $JobName --region $Region --wait

Write-Host "Migrations completed."
