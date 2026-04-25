param(
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [Parameter(Mandatory=$true)][string]$Region,
    [Parameter(Mandatory=$true)][string]$RepoName,
    [Parameter(Mandatory=$true)][string]$ServiceName,
    [Parameter(Mandatory=$true)][string]$Tag,
    [Parameter(Mandatory=$true)][string]$CloudSqlConnectionName
)

$ErrorActionPreference = 'Stop'

$Image = "$Region-docker.pkg.dev/$ProjectId/$RepoName/vixogram-web:$Tag"

gcloud config set project $ProjectId

Write-Host "Ensuring Artifact Registry repo exists..."
try {
    gcloud artifacts repositories describe $RepoName --location=$Region | Out-Null
} catch {
    gcloud artifacts repositories create $RepoName --repository-format=docker --location=$Region --description="Vixogram images"
}

Write-Host "Building and pushing image..."
gcloud builds submit --tag $Image .

Write-Host "Deploying Cloud Run web service..."
gcloud run deploy $ServiceName --image $Image --region $Region --platform managed --allow-unauthenticated --port 8080 --min-instances 0 --max-instances 5 --set-env-vars "ENVIRONMENT=production,DEBUG=0" --set-secrets "SECRET_KEY=SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest" --add-cloudsql-instances $CloudSqlConnectionName

Write-Host "Web deploy complete."
