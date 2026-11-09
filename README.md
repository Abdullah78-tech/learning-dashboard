
# Learning Dashboard

A full-stack learning platform under development.

## Tech Stack

- Frontend: React + Vite
- Backend: Python + FastAPI
- Database: SQLite for development, PostgreSQL supported
- ORM: SQLAlchemy
- Migrations: Alembic
- Authentication: Email/password, email OTP, Google OAuth, Facebook OAuth

## Project Structure

```text
learning-dashboard/
├── frontend/          # React application
├── backend/
│   ├── app/           # FastAPI application
│   ├── migrations/    # Database migrations
│   └── tests/         # Backend tests
├── .github/           # GitHub Actions
├── .gitignore
└── README.md
```

## Backend Setup (Windows PowerShell)

Open a terminal in the project directory:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Generate a secret key:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the generated key in `backend/.env` as `SECRET_KEY`.
Configure database, SMTP and OAuth credentials as needed.

Run migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Start FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Open http://localhost:8000.

## Frontend Setup

In another terminal, from the project root:

```powershell
cd frontend
npm install
npm run dev
```

The React frontend is currently a scaffold. Authentication and dashboard pages are still provided by the existing Python application until migration is completed.

## Running Backend Tests

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic current
```

## OAuth and Email Configuration

Use `backend/.env` for private credentials.

Google callback: `http://localhost:8000/auth/google/callback`

Facebook callback: `http://localhost:8000/auth/facebook/callback`

Use the `BASE_URL` value that matches your actual backend origin. Configure callbacks in the respective provider dashboards.

See `backend/README.md` for additional backend setup and troubleshooting information.

## Security

Never commit `.env` files, database contents, virtual environments, SMTP passwords or OAuth secrets.

## Development Status

This project is being reorganized into a React frontend and a FastAPI backend. The full-stack integration is not complete yet.
  