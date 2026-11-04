import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from authlib.integrations.base_client.errors import OAuthError
from .db import get_db as database_dependency
from .models import User, PendingSignup, Identity, LoginSession, now
from .security import (check_csrf, current_user, establish_login, hasher, keyed_digest,
                       password_valid, rate_limit, digest)
from .mailer import DeliveryError
from .views import render

router = APIRouter()

# Typed wrapper is required for FastAPI to inject Request rather than a query value.
def get_db(request: Request):
    yield from database_dependency(request)

DB = Annotated[Session, Depends(get_db)]


class SignupInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)


def redirect(path):
    return RedirectResponse(path, status_code=303)


def auth_page(request, mode, error=None, status=200, **values):
    return render(request, 'auth.html', status_code=status, mode=mode, error=error, **values)


def pending_for(request, db):
    pending_id = request.session.get('pending')
    return db.get(PendingSignup, pending_id) if pending_id else None


@router.get('/')
def home(request: Request, db: DB):
    return redirect('/dashboard' if current_user(request, db) else '/signin')


@router.get('/signup')
def signup_page(request: Request, db: DB):
    if current_user(request, db):
        return redirect('/dashboard')
    return auth_page(request, 'signup')


@router.get('/signin')
def signin_page(request: Request, db: DB):
    if current_user(request, db):
        return redirect('/dashboard')
    return auth_page(request, 'signin')


@router.post('/signup')
def signup(request: Request, db: DB, csrf: Annotated[str, Form()],
           name: Annotated[str, Form(max_length=100)], email: Annotated[str, Form(max_length=254)],
           password: Annotated[str, Form(max_length=128)]):
    check_csrf(request, csrf)
    settings = request.app.state.settings
    rate_limit(db, settings, 'signup-ip', request.client.host, 10, 3600)
    try:
        data = SignupInput(name=name.strip(), email=email.strip(), password=password)
    except ValidationError:
        return auth_page(request, 'signup', 'Use a valid email, a name of 2–100 characters, and a password of 12–128 characters.', 400, name=name, email=email)
    normalized = str(data.email).lower()
    rate_limit(db, settings, 'signup-email', normalized, 5, 3600)
    if db.scalar(select(User).where(User.email == normalized)):
        return auth_page(request, 'signup', 'An account with this email already exists. Please sign in using your original method.', 409)
    if not settings.mail_enabled:
        return auth_page(request, 'signup', 'Email signup is not configured yet. Set the SMTP values in your local .env file.', 503)
    identifier, code = secrets.token_urlsafe(32), f'{secrets.randbelow(1_000_000):06d}'
    pending = PendingSignup(id=identifier, name=data.name, email=normalized,
                            password_hash=hasher.hash(data.password),
                            code_hash=keyed_digest(settings, f'{identifier}:{code}'),
                            expires_at=now() + 600, sent_at=now())
    # No user account is created until the code is verified.
    try:
        request.app.state.send_otp(settings, normalized, code)
    except DeliveryError:
        return auth_page(request, 'signup', 'Email could not be sent. Check your SMTP configuration and try again.', 503)
    previous = pending_for(request, db)
    if previous:
        db.delete(previous)
    db.add(pending)
    db.commit()
    request.session['pending'] = identifier
    return redirect('/verify')


@router.get('/verify')
def verify_page(request: Request, db: DB):
    pending = pending_for(request, db)
    if not pending:
        return redirect('/signup')
    return render(request, 'verify.html', email=pending.email)


@router.post('/verify')
def verify(request: Request, db: DB, csrf: Annotated[str, Form()], code: Annotated[str, Form(max_length=20)]):
    check_csrf(request, csrf)
    settings = request.app.state.settings
    rate_limit(db, settings, 'verify-ip', request.client.host, 30, 600)
    pending_id = request.session.get('pending')
    # Locks serialize verification/resend on PostgreSQL.
    pending = db.scalar(select(PendingSignup).where(PendingSignup.id == pending_id).with_for_update())
    if not pending:
        return redirect('/signup')
    if pending.expires_at <= now() or pending.attempts >= 5:
        return render(request, 'verify.html', status_code=400, email=pending.email,
                      error='This code expired or has too many failed attempts. Request a new code.')
    if not secrets.compare_digest(pending.code_hash, keyed_digest(settings, f'{pending.id}:{code.strip()}')):
        db.execute(update(PendingSignup).where(PendingSignup.id == pending.id).values(attempts=PendingSignup.attempts + 1))
        db.commit()
        return render(request, 'verify.html', status_code=400, email=pending.email, error='Incorrect code. Please check your email and try again.')
    # Atomic conditional delete prevents concurrent replay even with SQLite.
    consumed = db.execute(delete(PendingSignup).where(
        PendingSignup.id == pending.id, PendingSignup.code_hash == pending.code_hash,
        PendingSignup.attempts < 5, PendingSignup.expires_at > now()))
    if consumed.rowcount != 1:
        db.rollback()
        return redirect('/signup')
    user = User(name=pending.name, email=pending.email, password_hash=pending.password_hash)
    db.add(user)
    try:
        db.flush()
        return establish_login(request, db, user.id, redirect('/dashboard'))
    except IntegrityError:
        db.rollback()
        return auth_page(request, 'signin', 'This email already has an account. Sign in using your original method.', 409)


@router.post('/resend')
def resend(request: Request, db: DB, csrf: Annotated[str, Form()]):
    check_csrf(request, csrf)
    settings = request.app.state.settings
    rate_limit(db, settings, 'resend-ip', request.client.host, 10, 3600)
    pending = db.scalar(select(PendingSignup).where(PendingSignup.id == request.session.get('pending')).with_for_update())
    if not pending:
        return redirect('/signup')
    if pending.sent_at + 60 > now() or pending.resends >= 3:
        return render(request, 'verify.html', status_code=429, email=pending.email,
                      error='Wait 60 seconds between emails. Each signup allows 3 resends; start again if you reached this limit.')
    code = f'{secrets.randbelow(1_000_000):06d}'
    # Reserve this resend before sending to prevent simultaneous resend requests.
    result = db.execute(update(PendingSignup).where(PendingSignup.id == pending.id,
        PendingSignup.sent_at == pending.sent_at, PendingSignup.resends == pending.resends).values(
        code_hash=keyed_digest(settings, f'{pending.id}:{code}'), sent_at=now(),
        expires_at=now() + 600, attempts=0, resends=PendingSignup.resends + 1))
    if result.rowcount != 1:
        db.rollback()
        return redirect('/verify')
    db.commit()
    try:
        request.app.state.send_otp(settings, pending.email, code)
    except DeliveryError:
        return render(request, 'verify.html', status_code=503, email=pending.email,
                      error='Email delivery failed. Wait 60 seconds and try again, or start signup again.')
    return render(request, 'verify.html', email=pending.email, success='A new code is on its way. Your previous code no longer works.')


@router.post('/signin')
def signin(request: Request, db: DB, csrf: Annotated[str, Form()],
           email: Annotated[str, Form(max_length=254)], password: Annotated[str, Form(max_length=128)]):
    check_csrf(request, csrf)
    settings = request.app.state.settings
    normalized = email.strip().lower()
    rate_limit(db, settings, 'signin-ip', request.client.host, 30, 900)
    rate_limit(db, settings, 'signin-email', normalized, 10, 900)
    user = db.scalar(select(User).where(User.email == normalized))
    valid = password_valid(user.password_hash if user else None, password)
    if not user or not user.password_hash or not valid:
        return auth_page(request, 'signin', 'Email or password is incorrect. If you registered with Google, continue with Google.', 400, email=email)
    return establish_login(request, db, user.id, redirect('/dashboard'))


@router.post('/logout')
def logout(request: Request, db: DB, csrf: Annotated[str, Form()]):
    check_csrf(request, csrf)
    raw = request.cookies.get('ld_auth')
    if raw:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(raw)))
        db.commit()
    request.session.clear()
    response = redirect('/signin')
    response.delete_cookie('ld_auth', path='/')
    return response


@router.post('/auth/google')
async def google_start(request: Request, csrf: Annotated[str, Form()]):
    check_csrf(request, csrf)
    if not request.app.state.settings.google_enabled:
        return auth_page(request, 'signin', 'Google login needs the Client ID and Client secret in your local .env file.', 503)
    try:
        return await request.app.state.oauth.google.authorize_redirect(
            request, request.app.state.settings.base_url + '/auth/google/callback', prompt='select_account')
    except Exception:
        return auth_page(request, 'signin', 'Google is temporarily unavailable. Please try again later.', 503)


def resolve_google_user(db, claims):
    if not claims.get('sub') or claims.get('email_verified') is not True:
        raise ValueError('Google did not return a verified email address.')
    normalized = str(claims.get('email', '')).lower()
    # Validate claims we persist; trust only the provider's validated token.
    from pydantic import TypeAdapter
    normalized = str(TypeAdapter(EmailStr).validate_python(normalized)).lower()
    identity = db.scalar(select(Identity).where(Identity.provider == 'google', Identity.subject == claims['sub']))
    if identity:
        return db.get(User, identity.user_id)
    if db.scalar(select(User).where(User.email == normalized)):
        # Explicit linking requires reauthentication, so never silently merge by email.
        raise ValueError('An account already uses this email. Sign in with your original method. Account linking is not available yet.')
    user = User(name=(claims.get('name') or normalized.split('@')[0])[:100], email=normalized)
    db.add(user)
    db.flush()
    db.add(Identity(user_id=user.id, provider='google', subject=claims['sub']))
    db.flush()
    return user


@router.get('/auth/google/callback')
async def google_callback(request: Request, db: DB):
    if not request.app.state.settings.google_enabled:
        return redirect('/signin')
    try:
        # Authlib verifies state, OIDC nonce, signature, issuer, audience and expiry.
        token = await request.app.state.oauth.google.authorize_access_token(request)
        claims = token.get('userinfo')
        if not claims:
            raise ValueError('Google did not return your account information. Please try again.')
        user = await run_in_threadpool(resolve_google_user, db, claims)
        return await run_in_threadpool(establish_login, request, db, user.id, redirect('/dashboard'))
    except (OAuthError, ValueError, IntegrityError):
        db.rollback()
        return auth_page(request, 'signin', 'Google sign-in could not be completed. Try again, or use your original sign-in method if this email already has an account.', 400)
    except Exception:
        db.rollback()
        return auth_page(request, 'signin', 'Google is temporarily unavailable. Please try again later.', 503)
