param(
  [ValidateSet('auto','sqlite','postgres','fixture')]
  [string]$Mode = 'auto',

  # Optional explicit output path. If omitted, a timestamped file is created under ./backups
  [string]$Out = ''
)

$ErrorActionPreference = 'Stop'

function New-Timestamp {
  return (Get-Date).ToString('yyyyMMdd_HHmmss')
}

function Ensure-BackupsDir {
  $dir = Join-Path $PSScriptRoot '..\backups'
  if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir | Out-Null
  }
  return (Resolve-Path $dir).Path
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot

try {
  $backupsDir = Ensure-BackupsDir
  $ts = New-Timestamp

  $dbPath = Join-Path $projectRoot 'db.sqlite3'
  $databaseUrl = ($env:DATABASE_URL ?? '').Trim()

  if ($Mode -eq 'auto') {
    if ($databaseUrl -match '^(postgres|postgresql)://') {
      $Mode = 'postgres'
    } elseif (Test-Path $dbPath) {
      $Mode = 'sqlite'
    } else {
      throw "Could not detect database. Set DATABASE_URL for Postgres or ensure db.sqlite3 exists for SQLite."
    }
  }

  if ($Mode -eq 'sqlite') {
    if (-not (Test-Path $dbPath)) {
      throw "SQLite db not found at: $dbPath"
    }
    if (-not $Out) {
      $Out = Join-Path $backupsDir "sqlite_$ts.sqlite3"
    }
    Copy-Item -Force $dbPath $Out
    Write-Host "SQLite backup created: $Out"
    exit 0
  }

  if ($Mode -eq 'postgres') {
    if (-not ($databaseUrl -match '^(postgres|postgresql)://')) {
      throw "DATABASE_URL is not set (or not postgres). Set it in your env/.env before running Postgres backup."
    }

    $pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
    if (-not $pgDump) {
      throw "pg_dump not found. Install PostgreSQL client tools, or use -Mode fixture as a fallback."
    }

    if (-not $Out) {
      $Out = Join-Path $backupsDir "postgres_$ts.dump"
    }

    # Custom format: smaller + supports pg_restore.
    & $pgDump.Source --dbname=$databaseUrl --format=custom --no-owner --no-privileges --file=$Out
    Write-Host "Postgres backup created: $Out"
    exit 0
  }

  if ($Mode -eq 'fixture') {
    if (-not $Out) {
      $Out = Join-Path $backupsDir "fixture_$ts.json"
    }

    # Portable JSON fixture. NOTE: restoring via loaddata is intended for EMPTY databases.
    # Exclude Django internals and permissions (they get recreated by migrate).
    python manage.py dumpdata \
      --natural-foreign \
      --natural-primary \
      --exclude contenttypes \
      --exclude auth.permission \
      --exclude admin.logentry \
      --indent 2 \
      --output $Out

    Write-Host "Fixture dump created: $Out"
    Write-Host "IMPORTANT: Don't loaddata this into production unless you know what you're doing (it can conflict with existing rows)."
    exit 0
  }

  throw "Unknown mode: $Mode"
}
finally {
  Pop-Location
}
