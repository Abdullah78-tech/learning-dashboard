"""Facebook authorization-code login. Access tokens stay on the server."""
import hashlib
import hmac
from typing import Annotated
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Form, Request
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from .auth import DB, auth_page, redirect
from .models import Identity, User
from .security import check_csrf, establish_login

router = APIRouter()


def resolve_facebook_user(db, profile):
    subject = profile.get('id')
    if not isinstance(subject, str) or not subject.isdigit() or len(subject) > 255:
        raise ValueError('Facebook did not return a valid account identifier. Please try again.')
    identity = db.scalar(select(Identity).where(Identity.provider == 'facebook', Identity.subject == subject))
    if identity:
        # A returning user is identified by app-scoped ID, never by email/name.
        return db.get(User, identity.user_id)
    if not profile.get('email'):
        raise ValueError('Facebook did not share an email address. Allow email access in Facebook, or sign up using email instead.')
    try:
        email = str(TypeAdapter(EmailStr).validate_python(profile['email'])).lower()
    except ValueError:
        raise ValueError('Facebook did not return a usable email address. Please sign up using email instead.') from None
    if len(email) > 254:
        raise ValueError('This email address is too long. Please use another sign-in method.')
    if db.scalar(select(User).where(User.email == email)):
        raise ValueError('An account already uses this email. Sign in with your original method. Account linking is not available yet.')
    name = profile.get('name')
    if not isinstance(name, str) or not name.strip():
        name = email.split('@')[0]
    user = User(email=email, name=name.strip()[:100])
    db.add(user)
    db.flush()
    db.add(Identity(user_id=user.id, provider='facebook', subject=subject))
    db.flush()
    return user


@router.post('/auth/facebook')
async def facebook_start(request: Request, csrf: Annotated[str, Form()]):
    check_csrf(request, csrf)
    settings = request.app.state.settings
    if not settings.facebook_enabled:
        return auth_page(request, 'signin', 'Facebook login needs the App ID and App Secret in your local .env file.', 503)
    try:
        return await request.app.state.oauth.facebook.authorize_redirect(
            request, settings.base_url + '/auth/facebook/callback')
    except Exception:
        return auth_page(request, 'signin', 'Facebook could not be reached. Please try again later.', 503)


@router.get('/auth/facebook/callback')
async def facebook_callback(request: Request, db: DB):
    settings = request.app.state.settings
    if not settings.facebook_enabled:
        return redirect('/signin')
    try:
        # Authlib checks single-use state before exchanging the authorization code.
        # Token exchange authenticates this app with its secret on the backend.
        token = await request.app.state.oauth.facebook.authorize_access_token(request)
        access_token = token.get('access_token')
        if not access_token:
            raise OAuthError(error='missing_token')
        proof = hmac.new(settings.facebook_app_secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()
        response = await request.app.state.oauth.facebook.get('me', token=token,
            params={'fields': 'id,name,email', 'appsecret_proof': proof})
        response.raise_for_status()
        profile = response.json()
        if not isinstance(profile, dict) or 'error' in profile:
            raise OAuthError(error='invalid_profile')
        user = await run_in_threadpool(resolve_facebook_user, db, profile)
        return await run_in_threadpool(establish_login, request, db, user.id, redirect('/dashboard'))
    except OAuthError:
        db.rollback()
        return auth_page(request, 'signin', 'Facebook sign-in was cancelled or expired. Please try again.', 400)
    except ValueError as exc:
        db.rollback()
        # Only our known account-resolution messages are safe to show; never expose provider data.
        message = str(exc)
        safe_prefixes = ('Facebook did not ', 'An account already ', 'This email address ')
        return auth_page(request, 'signin', message if message.startswith(safe_prefixes)
                         else 'Facebook returned an unexpected response. Please try again.', 400)
    except IntegrityError:
        db.rollback()
        return auth_page(request, 'signin', 'This account already exists. Please sign in using your original method.', 409)
    except Exception:
        db.rollback()
        return auth_page(request, 'signin', 'Facebook sign-in could not be completed. Check your Meta app settings and try again.', 503)
