# Backend development

The backend is a self-contained copy of the existing FastAPI/Jinja2 app. It retains the current UI and routes while React migration proceeds.

## Windows PowerShell

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the generated secret in `.env` as SECRET_KEY and configure SMTP/OAuth credentials privately. Do not commit .env.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Open http://localhost:8000. Use the same localhost hostname for OAuth callbacks as configured in BASE_URL.

## Notes
- Run commands from backend/ so `app` resolves to the copied package and `.env` is loaded from backend/.
- The root app/ remains available during migration.
- React frontend is a placeholder and does not yet use the backend.
- SQLite databases in different working directories are separate files. Existing local accounts do not automatically transfer.

## Troubleshooting Windows setup

### Pytest reports "No files were found in testpaths"

Run these commands from the repository root:

```powershell
git status
git branch --show-current
git pull --ff-only origin feat/frontend-backend-structure
cd backend
Get-ChildItem .\tests
```

The backend tests must include `test_auth.py` and `test_facebook.py`. If `git pull` reports a conflict or local changes, resolve those before attempting a checkout or reset. Run the tests from `backend/` with `.\.venv\Scripts\python.exe -m pytest -q`.

### SQLAlchemy native extension blocked by Windows Application Control

If importing SQLAlchemy fails with `DLL load failed ... An Application Control policy has blocked this file`, do **not** disable Windows security protections. SQLAlchemy supports building without its optional Cython extensions. From `backend/`:

```powershell
$env:DISABLE_SQLALCHEMY_CEXT = "1"
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --no-binary=SQLAlchemy --force-reinstall --no-deps "SQLAlchemy==2.1.8"
Remove-Item Env:\DISABLE_SQLALCHEMY_CEXT
.\.venv\Scripts\python.exe -c "import sqlalchemy; print(sqlalchemy.__version__)"
```

Only if that import succeeds, run `python -m alembic upgrade head` and then `python -m pytest -q` using the virtual environment executable. If a different native module is blocked, investigate the Windows Code Integrity events or request assistance from the PC administrator rather than switching off protection.
