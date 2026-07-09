from unittest.mock import patch, MagicMock
from urllib.parse import urlparse, parse_qs
from app.models.exchange_code import ExchangeCode
from app.models.user import User

REDIRECT_URI = 'http://localhost:3030/admin/scheduler_connection/callback'


def mock_flow(auth_url='https://accounts.google.com/o/oauth2/auth?mock=1'):
    flow = MagicMock()
    flow.authorization_url.return_value = (auth_url, 'google-state')
    credentials = MagicMock()
    credentials.token = 'gtoken'
    credentials.refresh_token = 'rtoken'
    credentials.token_uri = 'https://oauth2.googleapis.com/token'
    credentials.client_id = 'cid'
    credentials.client_secret = 'csecret'
    credentials.scopes = ['https://www.googleapis.com/auth/calendar']
    flow.credentials = credentials
    return flow


def mock_userinfo(email='connector@example.com'):
    oauth2 = MagicMock()
    oauth2.userinfo().get().execute.return_value = {'email': email}
    return oauth2


class TestConnect:
    def test_missing_params_returns_400(self, client):
        response = client.get('/connect')
        assert response.status_code == 400

    def test_disallowed_host_returns_400(self, client):
        response = client.get('/connect', query_string={
            'redirect_uri': 'https://evil.example.com/steal', 'state': 's'})
        assert response.status_code == 400
        assert 'not allowed' in response.json['error']

    def test_allowed_host_redirects_to_google(self, client):
        with patch('app.main.routes.build_oauth_flow', return_value=mock_flow()):
            response = client.get('/connect', query_string={
                'redirect_uri': REDIRECT_URI, 'state': 'hatan-state'})
        assert response.status_code == 302
        assert response.headers['Location'].startswith('https://accounts.google.com')


class TestCallbackRedirectBranch:
    def _oauth_patches(self):
        return (patch('app.main.routes.build_oauth_flow', return_value=mock_flow()),
                patch('app.main.routes.build', return_value=mock_userinfo()))

    def test_connect_in_progress_redirects_with_code(self, client, app):
        with client.session_transaction() as sess:
            sess['connect_redirect_uri'] = REDIRECT_URI
            sess['connect_state'] = 'hatan-state'
        p1, p2 = self._oauth_patches()
        with p1, p2:
            response = client.get('/callback?code=google-code&state=google-state')
        assert response.status_code == 302
        location = urlparse(response.headers['Location'])
        assert response.headers['Location'].startswith(REDIRECT_URI)
        params = parse_qs(location.query)
        assert params['state'] == ['hatan-state']
        with app.app_context():
            user = User.query.filter_by(email='connector@example.com').first()
            exchange = ExchangeCode.query.filter_by(code=params['code'][0]).first()
            assert exchange is not None
            assert exchange.user_id == user.id

    def test_no_connect_in_progress_returns_json_token(self, client, app):
        p1, p2 = self._oauth_patches()
        with p1, p2:
            response = client.get('/callback?code=google-code&state=google-state')
        assert response.status_code == 200
        assert 'token' in response.json
