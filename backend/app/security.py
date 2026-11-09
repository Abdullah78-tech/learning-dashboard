import hashlib
import hmac
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import LoginSession, RateBucket, PendingSignup, now

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 12 * 60 * 60


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def keyed_digest(settings, value):
    return hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def password_valid(encoded, password):
    try:
        return hasher.verify(encoded or DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False


def csrf_token(request):
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_urlsafe(32)
    return request.session['csrf']


def check_csrf(request, supplied):
    expected = request.session.get('csrf')
    if not isinstance(supplied, str) or not expected or not secrets.compare_digest(expected, supplied):
        raise HTTPException(403, 'This form expired. Reload the page and try again.')


def rate_limit(db, settings, label, identity, limit, seconds):
    timestamp = now()
    key = keyed_digest(settings, f'{label}:{identity}:{timestamp // seconds}')
    insert = sqlite_insert if db.bind.dialect.name == 'sqlite' else pg_insert
    statement = insert(RateBucket).values(key=key, count=1, expires_at=timestamp + seconds)
    statement = statement.on_conflict_do_update(index_elements=['key'], set_={'count': RateBucket.count + 1})
    count = db.execute(statement.returning(RateBucket.count)).scalar_one()
    # Garbage collection keeps anonymous traffic from leaving permanent rows.
    db.execute(delete(RateBucket).where(RateBucket.expires_at < timestamp))
    db.execute(delete(LoginSession).where(LoginSession.expires_at < timestamp))
    db.execute(delete(PendingSignup).where(PendingSignup.expires_at < timestamp - 86400))
    db.commit()
    if count > limit:
        raise HTTPException(429, 'Too many attempts. Please wait and try again.', headers={'Retry-After': str(seconds)})


def current_user(request, db):
    from .models import User
    raw = request.cookies.get('ld_auth')
    if not raw:
        return None
    record = db.get(LoginSession, digest(raw))
    if not record or record.expires_at <= now():
        return None
    return db.get(User, record.user_id)


def establish_login(request, db, user_id, response):
    old = request.cookies.get('ld_auth')
    if old:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(old)))
    raw = secrets.token_urlsafe(48)
    db.add(LoginSession(token_hash=digest(raw), user_id=user_id, expires_at=now() + SESSION_SECONDS))
    db.commit()
    request.session.clear()
    response.set_cookie('ld_auth', raw, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.app.state.settings.secure_cookies, samesite='lax', path='/')
    return response
