# Learning Dashboard migration

The existing FastAPI/Jinja2 app in app/ remains the working application. The new frontend/ is a React/Vite scaffold, not yet connected to authentication.

## Target folders
- frontend/src/pages: login, signup, OTP, dashboard screens
- frontend/src/components: reusable UI
- frontend/src/services: API client
- frontend/public: images and static assets
- backend/app/api: auth, Google, Facebook, dashboard routes
- backend/app/core: config and security
- backend/app/database: SQLAlchemy engine and models
- backend/app/schemas: request/response validation
- backend/app/services: OTP and email
- backend/migrations: existing Alembic versions
- backend/tests: authentication regression tests

## Safe sequence
1. Scaffold frontend without changing the working backend (this step).
2. Move backend code and update imports, Alembic, tests, CI, and documentation together.
3. Convert Jinja2 templates into React components.
4. Add JSON endpoints and preserve session cookies, CSRF and OAuth security.
5. Integrate signup, OTP, Google/Facebook login, and dashboard.
6. Test before merging.

Run frontend with cd frontend, npm install, npm run dev. The frontend is a placeholder until API integration. Never put SMTP or OAuth secrets in VITE_ variables.