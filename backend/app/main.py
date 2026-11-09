from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from authlib.integrations.starlette_client import OAuth
from .config import get_settings
from .db import create_database
from .auth import router, DB, redirect
from .security import current_user
from .views import render
from .mailer import send_otp
from .facebook import router as facebook_router
from .models import Identity
from sqlalchemy import select


def create_app(settings=None):
    settings = settings or get_settings()
    engine, session_factory = create_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.send_otp = send_otp
    oauth = OAuth()
    if settings.google_enabled:
        oauth.register(name='google', client_id=settings.google_client_id,
                       client_secret=settings.google_client_secret,
                       server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                       client_kwargs={'scope': 'openid email profile', 'timeout': 15})
    if settings.facebook_enabled:
        version = settings.facebook_api_version
        oauth.register(name='facebook', client_id=settings.facebook_app_id,
                       client_secret=settings.facebook_app_secret,
                       authorize_url=f'https://www.facebook.com/{version}/dialog/oauth',
                       access_token_url=f'https://graph.facebook.com/{version}/oauth/access_token',
                       api_base_url=f'https://graph.facebook.com/{version}/',
                       client_kwargs={'scope': 'public_profile,email',
                                      'token_endpoint_auth_method': 'client_secret_post', 'timeout': 15})
    app.state.oauth = oauth
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie='ld_flow',
                       same_site='lax', https_only=settings.secure_cookies, max_age=3600)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlparse(settings.base_url).hostname, 'localhost', '127.0.0.1', 'testserver'])

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        # Chromium applies form-action to redirects from the Google login POST.
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://accounts.google.com https://www.facebook.com"
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if not request.url.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        if settings.secure_cookies:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc):
        response = render(request, 'error.html', status_code=exc.status_code, code=exc.status_code,
                          message=str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    app.mount('/static', StaticFiles(directory=str(Path(__file__).parent / 'static')), name='static')
    app.include_router(router)
    app.include_router(facebook_router)

    @app.get('/dashboard', response_class=HTMLResponse)
    def dashboard(request: Request, db: DB):
        user = current_user(request, db)
        if not user:
            return redirect('/signin')
        provider = db.scalar(select(Identity.provider).where(Identity.user_id == user.id))
        return render(request, 'dashboard.html', user=user, login_method=provider or 'password')

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    return app
