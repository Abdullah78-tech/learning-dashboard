# Learning Dashboard

A Python authentication starter with a blue-and-white dashboard inspired by the supplied reference. The dashboard is a **design prototype**; its charts, projects and integrations use clearly marked sample data.

## What works

- Email signup → six-digit email OTP → verified account → dashboard.
- Email/password sign-in without an OTP.
- Google account selection and login using OAuth/OpenID Connect, after local credentials are configured.
- Facebook login using a server-side OAuth authorization-code flow, after Meta app credentials are configured.
- Protected dashboard, real profile details and sign-out with server-side session revocation.
- Responsive dashboard navigation, mobile menu, password visibility toggle and demo feedback.

Google and Facebook buttons appear on both auth pages and enable when their credentials are configured. Password reset, account linking, profile editing and dashboard business features remain future work.

## Run on Windows (PowerShell)

Install **Python 3.12+** and Git, then run:

```powershell
git clone https://github.com/Abdullah78-tech/learning-dashboard.git
cd learning-dashboard
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Open `.env` in VS Code. Replace `SECRET_KEY` with the generated value. Fill in Google and SMTP settings described below. Do not share this file. You do not need to activate PowerShell scripts; use the virtual environment's Python executable directly.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Open **http://localhost:8000**. Use `localhost` consistently during Google login, not `127.0.0.1`. Stop with Ctrl+C. Google/email signup are unavailable until their settings are supplied; there is no automatic authentication bypass.

On Linux/macOS use `python3 -m venv .venv`, `cp .env.example .env` and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python` in the commands.

## Database: SQLite first, PostgreSQL when ready

The quick-start uses a local SQLite file so you can start without installing a database service or paying for hosting. PostgreSQL support is included through SQLAlchemy and Psycopg and is the intended choice as this project grows.

For PostgreSQL, create a database and an application role with a password using pgAdmin or your PostgreSQL administrator account, then set:

```dotenv
DATABASE_URL=postgresql+psycopg://dashboard:YOUR_URL_ENCODED_PASSWORD@localhost:5432/learning_dashboard
```

The role must own the database or have schema permissions for migrations. Percent-encode special characters in the URL password. Run `python -m alembic upgrade head` with your virtual environment after changing the URL. SQLite records are **not** automatically copied into PostgreSQL. Do not use real customer data for these experiments.

Database migrations are versioned in `migrations/`. Future schema changes should use new Alembic revisions rather than editing the existing initial revision.

## Google login

Use your existing Google Cloud project and Web application OAuth client:

| Google setting | Value |
| --- | --- |
| JavaScript origin | `http://localhost` |
| Additional origin | `http://localhost:8000` |
| Authorized redirect URI | `http://localhost:8000/auth/google/callback` |

In `.env`:

```dotenv
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
BASE_URL=http://localhost:8000
```

The implementation uses a server-side authorization-code flow. The redirect URI is essential; JavaScript origins are retained for compatibility with your existing setup. Requests use `openid email profile` and `prompt=select_account`. Google decides which accounts are visible in the current browser session. Basic sign-in does not request Gmail/Drive access.

Keep the Google app in Testing during development. Add your personal account to its test users where applicable. Restart the local server after editing settings. The first Google login creates a user; subsequent logins identify that user by Google's stable `sub`, not their display name. An existing email/password account is not silently merged with Google: sign in using the original method. Explicit account linking is deferred.

Official setup: https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid

## Facebook login (Meta app setup)

1. Open https://developers.facebook.com/apps/ and create an app for Facebook Login/user authentication. Use the ordinary Facebook Login use case for a consumer website, not a business-management/ads integration. Dashboard wording can vary.
2. Keep it in Development/testing mode. Use your app administrator/developer account or an accepted tester role for testing; enabling the code does not make Meta grant access to every Facebook user.
3. In Facebook Login settings, enable Client OAuth Login and Web OAuth Login where shown. Configure the website platform/site URL for your development site.
4. The callback used by this project is **`http://localhost:8000/auth/facebook/callback`**. Configure the exact callback using Meta's redirect settings. Localhost handling depends on development mode and the current dashboard. If the dashboard says localhost redirects are automatically allowed, do not force a rejected entry. If it requires HTTPS, use a properly configured HTTPS development origin and update `BASE_URL`, cookies and both providers' callbacks consistently; do not switch the app to Live merely to test.
5. Enable/request `public_profile` and `email` in the Facebook Login use case. The user must share an email for a new account; Facebook may not return an email even when requested.
6. Copy the App ID and App Secret from the app's settings privately into your local `.env`:

```dotenv
FACEBOOK_APP_ID=your-meta-app-id
FACEBOOK_APP_SECRET=your-meta-app-secret
FACEBOOK_API_VERSION=v22.0
```

The API version is configurable. `v22.0` is the implementation default, not a claim that it is the latest. Use a supported version shown in your Meta app dashboard when appropriate. Restart the Python server and open `http://localhost:8000/signin` to test. Meta controls the login/consent UI and may reuse the browser's existing Facebook session; it does not offer Google's account picker behavior.

The app sends users to Facebook, validates OAuth state, exchanges the code on the backend, and fetches `id,name,email` with an app-secret proof. Access tokens are neither stored in browser cookies nor persisted in the database. Returning users are matched by their app-scoped Facebook ID. An email already used by another account is never automatically linked. If Facebook omits email, the user receives an explanation and can use email signup instead. Facebook email is not presented as independently OTP-verified.

Live public use needs the Meta publishing requirements shown for your app, including suitable public privacy and data-deletion information and any required permissions review. These public-launch requirements and pages are outside this local learning setup. Do not paste credentials into screenshots, source code or chat.

Provider reference: https://developers.facebook.com/docs/facebook-login/manually-build-a-login-flow/

## Send OTPs from your personal email

If your mailbox is **Gmail**:

1. Enable 2-Step Verification in your Google Account.
2. Create an App Password at https://myaccount.google.com/apppasswords if your account offers it.
3. Store the generated App Password locally. Do not use your normal Gmail password.
4. Set these values in `.env`:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=your-app-password-without-display-spaces
SMTP_FROM=your-address@gmail.com
```

Some accounts do not offer app passwords (for example, due to account security or organisation policy). If unavailable, use a mailbox/provider that supports authenticated SMTP, or add Gmail OAuth mail delivery in a future change. Do not disable your account security settings to make SMTP work.

For another personal email provider, use its documented SMTP host, port and app-password requirements. This app supports STARTTLS (typically port 587) or implicit TLS (`SMTP_SECURITY=ssl`, typically 465); it never sends credentials over plaintext SMTP.

Google OAuth credentials and the SMTP app password are separate. Google login does not configure email delivery. Mailbox sending limits still apply; this starter is for low-volume learning, not bulk email.

Official Gmail help: https://support.google.com/mail/answer/185833

## How the project is organised

| Path | Purpose |
| --- | --- |
| `app/main.py` | Application factory, protected dashboard and response headers |
| `app/auth.py` | Signup, verification, resend, sign-in, logout and Google routes |
| `app/facebook.py` | Facebook OAuth routes and identity handling |
| `app/config.py` | Validated environment settings |
| `app/models.py`, `app/db.py` | Users, identities, pending signups, sessions, rate limits |
| `app/security.py` | Password hashing, CSRF, session and rate-limit helpers |
| `app/mailer.py` | SMTP delivery |
| `app/templates/`, `app/static/` | HTML, CSS, JavaScript and SVG assets |
| `migrations/` | Alembic migrations |
| `tests/` | Authentication regression tests |

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use temporary SQLite databases and a fake in-memory mail sender. They do not send real emails. OAuth tests cover identity mapping, redirect parameters, invalid state and simulated callback handling; live Google/Facebook login and real SMTP delivery still need your local credentials and a manual end-to-end check. GitHub Actions also exercises PostgreSQL.

## Security and scope

Passwords use Argon2id. OTPs are generated cryptographically, stored as keyed hashes, expire after 10 minutes and allow five incorrect attempts. Resends wait 60 seconds and are capped at three per signup. Signup/sign-in have shared database-backed IP/email rate limits. Accounts are created only after verification, preventing an unverified password from being attached to a Google account.

Authentication uses opaque, HttpOnly, SameSite cookies and hashed server-side session records expiring after 12 hours. Logout revokes the record. Signed flow cookies contain CSRF/OAuth state and a pending challenge ID, never passwords or OTPs. Forms use CSRF tokens. Templates escape user data. Responses include CSP and no-store headers. Avoid logging OAuth callback query strings; the provided server command disables access logs.

This is a learning foundation, not a claim of production readiness. Before public use, add password recovery, monitoring, backup/restore, delivery queues, a scalable rate-limit design, abuse protection, public privacy/terms pages and provider verification as required. Set HTTPS `BASE_URL` and `SECURE_COOKIES=true`. Configure any reverse proxy to trust forwarding headers **only from your proxy**, redact callback query strings, and enforce request body limits. Production auth and rate-limit behavior need load and security review.

## Troubleshooting

- **SECRET_KEY error:** generate a random value; the placeholder is intentionally rejected.
- **no such table:** run `python -m alembic upgrade head` from the repository folder.
- **Google button disabled:** populate both Google settings and restart.
- **redirect_uri_mismatch:** compare the complete callback URL including port and path.
- **Code not received:** verify SMTP settings, check spam, and use an App Password for Gmail.
- **Too many attempts:** wait for the displayed limit window; don't repeatedly resend.
- **Email already exists with Google:** use the original sign-in method. Automatic account linking is intentionally unavailable.
- **Facebook button disabled:** fill `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET` in `.env`, then restart.
- **Facebook app unavailable:** check app mode, accepted tester/admin roles, enabled login use case and permissions.
- **Facebook missing email:** allow email access if offered, or use email signup.
- **Facebook redirect blocked:** verify the exact callback and that your local code includes the Facebook CSP allowlist.
- **Profile says Facebook connected:** this confirms provider login, not separate email OTP verification.

GitHub stores the source code. It does not run the Python backend through GitHub Pages. Local testing requires no paid hosting or domain.
