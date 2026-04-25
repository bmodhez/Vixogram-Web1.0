param(
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [Parameter(Mandatory=$true)][string]$Region,
    [Parameter(Mandatory=$true)][string]$InstanceName,
    [Parameter(Mandatory=$true)][string]$DbName,
    [Parameter(Mandatory=$true)][string]$DbUser,
    [Parameter(Mandatory=$true)][string]$DbPassword
)

$ErrorActionPreference = 'Stop'

gcloud config set project $ProjectId

Write-Host "Creating Cloud SQL Postgres instance (small shared-core)..."
gcloud sql instances create $InstanceName --database-version=POSTGRES_15 --cpu=1 --memory=3840MiB --region=$Region --storage-size=10GB --storage-type=SSD --availability-type=zonal

Write-Host "Creating DB and user..."
gcloud sql databases create $DbName --instance=$InstanceName
gcloud sql users create $DbUser --instance=$InstanceName --password=$DbPassword

$conn = gcloud sql instances describe $InstanceName --format="value(connectionName)"
Write-Host "Cloud SQL connection name: $conn"
Write-Host "Use this in Cloud Run: --add-cloudsql-instances=$conn"
