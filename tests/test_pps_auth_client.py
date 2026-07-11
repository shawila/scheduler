from unittest.mock import patch, MagicMock
import pytest
from app.pps_auth import fetch_google_access_token, GrantRevoked, PpsAuthError
from app.google_calendar import google_credentials_for
from app.models.user import User


def response(status, body=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body or {}
    return resp


class TestFetchGoogleAccessToken:
    def test_returns_access_token(self, monkeypatch):
        monkeypatch.setenv('SCHEDULER_PPS_CLIENT_SECRET', 'sekrit')
        with patch('app.pps_auth.requests.post', return_value=response(200, {'access_token': 'ya29.x', 'expires_in': 3599})) as mock_post:
            token = fetch_google_access_token('uuid-1')
        assert token == 'ya29.x'
        _, kwargs = mock_post.call_args
        assert kwargs['json'] == {'user_id': 'uuid-1'}
        assert kwargs['auth'] is not None

    def test_403_raises_grant_revoked(self, monkeypatch):
        monkeypatch.setenv('SCHEDULER_PPS_CLIENT_SECRET', 'sekrit')
        with patch('app.pps_auth.requests.post', return_value=response(403, {'error': 'grant_revoked'})):
            with pytest.raises(GrantRevoked):
                fetch_google_access_token('uuid-1')

    def test_other_error_raises_pps_auth_error(self, monkeypatch):
        monkeypatch.setenv('SCHEDULER_PPS_CLIENT_SECRET', 'sekrit')
        with patch('app.pps_auth.requests.post', return_value=response(502, {'error': 'upstream_error'})):
            with pytest.raises(PpsAuthError):
                fetch_google_access_token('uuid-1')


class TestGoogleCredentialsFor:
    def test_pps_user_uses_exchange(self, app):
        user = User(email='shell@example.com', pps_user_id='uuid-1')
        with patch('app.google_calendar.fetch_google_access_token', return_value='ya29.x') as mock_fetch:
            creds = google_credentials_for(user)
        mock_fetch.assert_called_once_with('uuid-1')
        assert creds.token == 'ya29.x'
        assert creds.refresh_token is None

    def test_legacy_user_uses_stored_tokens(self, app, store):
        with app.app_context():
            creds = google_credentials_for(store)
        assert creds.token == 'fake-token'
        assert creds.refresh_token == 'fake-refresh-token'


class TestErrorHandlers:
    def test_grant_revoked_maps_to_401(self, client, authed_user, org_with_owner):
        with patch('app.org.routes.google_credentials_for', side_effect=GrantRevoked('revoked')):
            resp = client.get(f'/org/{org_with_owner}/availability',
                              query_string={'date': '2026-08-01'},
                              headers={'Authorization': 'Bearer owner-api-token'})
        assert resp.status_code == 401
        assert 'revoked' in resp.json['error']

    def test_pps_auth_error_maps_to_503(self, client, authed_user, org_with_owner):
        with patch('app.org.routes.google_credentials_for', side_effect=PpsAuthError('down')):
            resp = client.get(f'/org/{org_with_owner}/availability',
                              query_string={'date': '2026-08-01'},
                              headers={'Authorization': 'Bearer owner-api-token'})
        assert resp.status_code == 503
