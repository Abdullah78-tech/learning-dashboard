import hashlib
import hmac
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from sqlalchemy import select, func
from app.models import User, Identity
from app.facebook import resolve_facebook_user
from test_auth import setup, csrf, signup, verify


def enable_facebook(app, profile=None, token_error=False):
    settings = app.state.settings
    settings.facebook_app_id = '123456'
    settings.facebook_app_secret = 'test-only-facebook-secret'
    requests = []
    def provider(request):
        requests.append(request)
        if request.url.path.endswith('/oauth/access_token'):
            body = parse_qs(request.content.decode())
            assert body['client_id'] == ['123456']
            assert body['client_secret'] == ['test-only-facebook-secret']
            assert body['redirect_uri'] == ['http://localhost:8000/auth/facebook/callback']
            if token_error:
                return httpx.Response(400, json={'error': 'invalid_grant'})
            return httpx.Response(200, json={'access_token': 'test-access-token', 'token_type': 'bearer', 'expires_in': 3600})
        assert request.url.path.endswith('/me')
        assert request.headers['authorization'].lower() == 'bearer test-access-token'
        assert request.url.params['fields'] == 'id,name,email'
        assert request.url.params['appsecret_proof'] == hmac.new(
            b'test-only-facebook-secret', b'test-access-token', hashlib.sha256).hexdigest()
        return httpx.Response(200, json=profile if profile is not None else
                              {'id': '998877', 'name': 'Facebook Learner', 'email': 'facebook@example.com'})
    app.state.oauth.register(name='facebook', client_id=settings.facebook_app_id,
        client_secret=settings.facebook_app_secret,
        authorize_url='https://www.facebook.com/v22.0/dialog/oauth',
        access_token_url='https://graph.facebook.com/v22.0/oauth/access_token',
        api_base_url='https://graph.facebook.com/v22.0/',
        client_kwargs={'scope': 'public_profile,email', 'token_endpoint_auth_method': 'client_secret_post',
                       'transport': httpx.MockTransport(provider)})
    return requests


def start(client):
    response = client.post('/auth/facebook', data={'csrf': csrf(client, '/signin')})
    assert response.status_code == 302
    url = urlparse(response.headers['location'])
    assert url.hostname == 'www.facebook.com'
    query = parse_qs(url.query)
    assert query['scope'] == ['public_profile,email']
    assert query['redirect_uri'] == ['http://localhost:8000/auth/facebook/callback']
    assert 'client_secret' not in query
    return query['state'][0]


def test_disabled_buttons_and_csrf(setup):
    app, client, _ = setup
    for path in ['/signin', '/signup']:
        html = client.get(path).text
        assert 'action="/auth/facebook"' in html
        assert 'Facebook needs configuration.' in html
    assert client.post('/auth/facebook', data={'csrf': 'wrong'}).status_code == 403
    assert client.post('/auth/facebook', data={'csrf': csrf(client)}).status_code == 503
    assert client.get('/auth/facebook/callback').headers['location'] == '/signin'


def test_real_oauth_flow_with_mock_provider_and_replay(setup):
    app, client, emails = setup
    calls = enable_facebook(app)
    state = start(client)
    response = client.get('/auth/facebook/callback', params={'code': 'test-code', 'state': state})
    assert response.headers['location'] == '/dashboard'
    assert len(calls) == 2 and not emails
    assert 'test-access-token' not in str(client.cookies)
    html = client.get('/dashboard').text
    assert 'Facebook Learner' in html and '<dd>Facebook</dd>' in html
    assert 'Facebook connected' in html
    client.post('/logout', data={'csrf': csrf(client, '/dashboard')})
    assert client.get('/auth/facebook/callback', params={'code': 'test-code', 'state': state}).status_code == 400
    assert len(calls) == 2
    state = start(client)
    assert client.get('/auth/facebook/callback', params={'code': 'second-code', 'state': state}).status_code == 303
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Identity)) == 1


def test_invalid_state_and_cancellation_do_not_create_users(setup):
    app, client, _ = setup
    calls = enable_facebook(app)
    state = start(client)
    assert client.get('/auth/facebook/callback?code=x&state=wrong').status_code == 400
    assert client.get('/auth/facebook/callback', params={'error': 'access_denied', 'state': state}).status_code == 400
    assert not calls
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize('profile', [{'id': '123', 'name': 'No email'}, {'id': '123', 'email': 'not-an-email'}, {'email': 'person@example.com'}])
def test_unusable_profile_is_explained(setup, profile):
    app, client, _ = setup
    enable_facebook(app, profile)
    state = start(client)
    response = client.get('/auth/facebook/callback', params={'code': 'x', 'state': state})
    assert response.status_code == 400
    assert 'Facebook did not' in response.text
    assert client.get('/dashboard').headers['location'] == '/signin'


def test_no_automatic_linking_with_existing_password_account(setup):
    app, client, emails = setup
    signup(client, email='facebook@example.com'); verify(client, emails[-1][1])
    client.post('/logout', data={'csrf': csrf(client, '/dashboard')})
    enable_facebook(app)
    state = start(client)
    response = client.get('/auth/facebook/callback', params={'code': 'x', 'state': state})
    assert response.status_code == 400 and 'original method' in response.text
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Identity)) == 0


def test_returning_facebook_user_uses_subject_not_email(setup):
    app, client, _ = setup
    with app.state.session_factory() as db:
        user = resolve_facebook_user(db, {'id':'123','email':'old@example.com','name':'Original'}); db.commit()
        assert resolve_facebook_user(db, {'id':'123'}).id == user.id
        assert resolve_facebook_user(db, {'id':'123','email':'different@example.com'}).id == user.id
        assert user.email == 'old@example.com'


def test_failed_token_exchange(setup):
    app, client, _ = setup
    calls = enable_facebook(app, token_error=True)
    state = start(client)
    response = client.get('/auth/facebook/callback', params={'code': 'x', 'state': state})
    assert response.status_code == 400 and len(calls) == 1
    assert 'test-only-facebook-secret' not in response.text
