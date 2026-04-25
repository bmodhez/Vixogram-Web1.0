param(
    [Parameter(Mandatory=$true)][string]$ProjectId
)

$ErrorActionPreference = 'Stop'

Write-Host "Setting active project: $ProjectId"
gcloud config set project $ProjectId

Write-Host "Enabling required APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com servicenetworking.googleapis.com

Write-Host "Done. APIs are enabled."
