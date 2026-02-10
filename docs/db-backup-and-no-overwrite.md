# DB backup + production overwrite safety

## Goal
When you deploy new code to production, your local dummy users/messages **must not** overwrite the production database.

## How this project is already designed
- **Local/dev** uses SQLite: `db.sqlite3`
- **Production** (Render) should use Postgres via `DATABASE_URL`
- In [`render.yaml`](../render.yaml) `ENVIRONMENT=production` is set, and in [`a_core/settings.py`](../a_core/settings.py) production **requires** `DATABASE_URL`.

So a normal deploy updates **code only** (plus migrations). It does **not** push your local data.

## What you must NOT do
- Don’t commit or deploy `db.sqlite3` (it’s gitignored).
- Don’t run `python manage.py loaddata <local_dump.json>` on production.

## Make a dump/backup file (safe)
All backups go into `./backups/` (gitignored).

Note: `backup_db.ps1 -Mode postgres` uses `DATABASE_URL` from your environment. Be careful not to keep production credentials in your local `.env` unless you intentionally want to back up production.

### 1) Local SQLite backup (fastest)
```powershell
.\scripts\backup_db.ps1 -Mode sqlite
```

### 2) Production Postgres backup (recommended)
Prereqs:
- `DATABASE_URL` available in your environment
- Postgres client tools installed (so `pg_dump` exists)

```powershell
$env:DATABASE_URL = "<your postgres url>"
.\scripts\backup_db.ps1 -Mode postgres
```

This creates a `.dump` file you can restore with `pg_restore` (typically into a new/empty database).

### 3) Portable JSON fixture (fallback)
```powershell
.\scripts\backup_db.ps1 -Mode fixture
```

Note: fixtures are best for **empty DB** restores (they can conflict with existing rows).

## Deploy checklist (no overwrite)
- Render Dashboard: set `DATABASE_URL`
- Deploy code
- Run migrations (Render start command already runs `python manage.py migrate --noinput`)
- Optional: keep a backup before risky changes using the script above
