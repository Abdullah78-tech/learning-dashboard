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
