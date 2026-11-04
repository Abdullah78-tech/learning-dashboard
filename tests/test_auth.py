import re
import os
import secrets
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update, func
from app.main import create_app
from app.config import Settings
from app.db import Base
from app.models import User, PendingSignup, LoginSession, now
from app.auth import resolve_google_user
from app.mailer import DeliveryError

@pytest.fixture
def setup(tmp_path):
    settings = Settings(_env_file=None, secret_key=secrets.token_urlsafe(48),
        database_url=os.environ.get('TEST_DATABASE_URL', f'sqlite:///{tmp_path}/test.db'), smtp_username='sender@example.com',
        smtp_password='test-only', smtp_from='sender@example.com')
    app = create_app(settings)
    Base.metadata.drop_all(app.state.engine)
    Base.metadata.create_all(app.state.engine)
    emails = []
    app.state.send_otp = lambda settings, email, code: emails.append((email, code))
    with TestClient(app, follow_redirects=False) as client:
        yield app, client, emails
    Base.metadata.drop_all(app.state.engine)
    app.state.engine.dispose()

def csrf(client, path='/signup'):
    page = client.get(path)
    return re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)

def signup(client, email='learner@example.com', name='Abdullah'):
    return client.post('/signup', data={'csrf': csrf(client), 'name': name,
        'email': email, 'password': 'a-long-learning-password'})

def verify(client, code):
    return client.post('/verify', data={'csrf': csrf(client, '/verify'), 'code': code})

def test_full_email_flow_and_logout_revocation(setup):
    app, client, emails = setup
    assert client.get('/dashboard').status_code == 303
    assert signup(client).headers['location'] == '/verify'
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        pending = db.scalar(select(PendingSignup))
        assert pending.code_hash != emails[-1][1]
        assert pending.password_hash.startswith('$argon2')
    response = verify(client, emails[-1][1])
    assert response.headers['location'] == '/dashboard'
    assert 'HttpOnly' in response.headers.get_list('set-cookie')[0]
    page = client.get('/dashboard')
    assert page.status_code == 200 and 'Abdullah' in page.text and 'Sample data' in page.text
    saved_cookie = client.cookies.get('ld_auth')
    assert client.post('/logout', data={'csrf': csrf(client, '/dashboard')}).status_code == 303
    client.cookies.set('ld_auth', saved_cookie)
    assert client.get('/dashboard').headers['location'] == '/signin'
    client.cookies.clear()
    result = client.post('/signin', data={'csrf': csrf(client, '/signin'), 'email': 'LEARNER@example.com', 'password': 'a-long-learning-password'})
    assert result.headers['location'] == '/dashboard'
    assert len(emails) == 1

def test_bad_codes_lock_after_five_and_expire(setup):
    app, client, emails = setup
    signup(client)
    wrong = '000000' if emails[-1][1] != '000000' else '111111'
    for _ in range(5):
        assert verify(client, wrong).status_code == 400
    assert verify(client, emails[-1][1]).status_code == 400
    with app.state.session_factory() as db:
        db.execute(update(PendingSignup).values(attempts=0, expires_at=now()-1)); db.commit()
    assert verify(client, emails[-1][1]).status_code == 400

def test_resend_cooldown_and_old_code_invalidated(setup):
    app, client, emails = setup
    signup(client)
    old = emails[-1][1]
    assert client.post('/resend', data={'csrf': csrf(client, '/verify')}).status_code == 429
    with app.state.session_factory() as db:
        db.execute(update(PendingSignup).values(sent_at=now()-61)); db.commit()
    assert client.post('/resend', data={'csrf': csrf(client, '/verify')}).status_code == 200
    assert len(emails) == 2
    if emails[-1][1] != old:
        assert verify(client, old).status_code == 400
    assert verify(client, emails[-1][1]).status_code == 303
    assert client.post('/verify', data={'csrf': csrf(client, '/dashboard'), 'code': emails[-1][1]}).headers['location'] == '/signup'

def test_csrf_and_unverified_signin(setup):
    app, client, emails = setup
    assert client.post('/signup', data={'csrf': 'bad', 'name': 'Abdullah', 'email': 'a@example.com', 'password': 'a-long-learning-password'}).status_code == 403
    signup(client)
    assert client.post('/signin', data={'csrf': csrf(client, '/signin'), 'email': 'learner@example.com', 'password': 'a-long-learning-password'}).status_code == 400
    assert client.get('/logout').status_code == 405

def test_email_delivery_failure_does_not_create_user(setup):
    app, client, emails = setup
    def fail(*args):
        raise DeliveryError('test failure')
    app.state.send_otp = fail
    assert signup(client).status_code == 503
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(PendingSignup)) == 0

def test_google_disabled_and_invalid_state(setup):
    app, client, emails = setup
    assert client.post('/auth/google', data={'csrf': csrf(client, '/signin')}).status_code == 503
    app.state.settings.google_client_id = 'test-id'
    app.state.settings.google_client_secret = 'test-secret'
    app.state.oauth.register(name='google', client_id='test-id', client_secret='test-secret',
        authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
        access_token_url='https://oauth2.googleapis.com/token', client_kwargs={'scope': 'openid email profile'})
    response = client.post('/auth/google', data={'csrf': csrf(client, '/signin')})
    assert response.status_code == 302
    assert 'prompt=select_account' in response.headers['location']
    assert 'state=' in response.headers['location'] and 'nonce=' in response.headers['location']
    assert client.get('/auth/google/callback?code=bad&state=wrong').status_code == 400

def test_google_identity_mapping_and_no_implicit_linking(setup):
    app, client, emails = setup
    claims = {'sub': 'google-123', 'email': 'google@example.com', 'email_verified': True, 'name': 'Google Learner'}
    with app.state.session_factory() as db:
        user = resolve_google_user(db, claims); db.commit()
        assert resolve_google_user(db, claims).id == user.id
        with pytest.raises(ValueError):
            resolve_google_user(db, {**claims, 'sub': 'other-sub'})
        with pytest.raises(ValueError):
            resolve_google_user(db, {**claims, 'email_verified': False})

def test_rate_limit(setup):
    app, client, emails = setup
    token = csrf(client, '/signin')
    for _ in range(10):
        assert client.post('/signin', data={'csrf': token, 'email': 'none@example.com', 'password': 'bad'}).status_code == 400
    response = client.post('/signin', data={'csrf': token, 'email': 'none@example.com', 'password': 'bad'})
    assert response.status_code == 429 and 'Retry-After' in response.headers

def test_escaped_profile_and_security_headers(setup):
    app, client, emails = setup
    signup(client, name='<script>alert(1)</script>')
    verify(client, emails[-1][1])
    response = client.get('/dashboard')
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']

def test_expired_session_and_duplicate_signup(setup):
    app, client, emails = setup
    signup(client); verify(client, emails[-1][1])
    with app.state.session_factory() as db:
        db.execute(update(LoginSession).values(expires_at=now()-1)); db.commit()
    assert client.get('/dashboard').headers['location'] == '/signin'
    assert signup(client).status_code == 409

def test_safe_configuration():
    with pytest.raises(ValueError):
        Settings(_env_file=None, secret_key='short')
    with pytest.raises(ValueError):
        Settings(_env_file=None, secret_key='x'*48, base_url='http://example.com')

def test_google_callback_success_with_validated_claims_mock(setup):
    app, client, emails = setup
    app.state.settings.google_client_id = 'test-id'
    app.state.settings.google_client_secret = 'test-secret'
    class FakeGoogle:
        async def authorize_access_token(self, request):
            return {'userinfo': {'sub': 'verified-provider-subject', 'email': 'google@example.com',
                                  'email_verified': True, 'name': 'Google Learner'}}
    from types import SimpleNamespace
    app.state.oauth = SimpleNamespace(google=FakeGoogle())
    assert client.get('/auth/google/callback').headers['location'] == '/dashboard'
    assert 'Google Learner' in client.get('/dashboard').text
    assert len(emails) == 0

def test_pending_signup_cannot_capture_google_account(setup):
    app, client, emails = setup
    signup(client, email='google@example.com')
    with app.state.session_factory() as db:
        user = resolve_google_user(db, {'sub': 'google-owner', 'email': 'google@example.com',
                                       'email_verified': True, 'name': 'Owner'})
        db.commit()
        assert user.password_hash is None
    assert verify(client, emails[-1][1]).status_code == 409
    assert client.get('/dashboard').headers['location'] == '/signin'
    with app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.email == 'google@example.com'))
        assert user.password_hash is None and user.name == 'Owner'

def test_resend_limit(setup):
    app, client, emails = setup
    signup(client)
    with app.state.session_factory() as db:
        db.execute(update(PendingSignup).values(sent_at=now()-61, resends=3)); db.commit()
    assert client.post('/resend', data={'csrf': csrf(client, '/verify')}).status_code == 429
    assert len(emails) == 1
