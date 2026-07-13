from unittest.mock import patch
from app.models.user import User


class TestTokenRevoke:
    def test_revoke_clears_api_token(self, client, app, authed_user):
        response = client.post('/token/revoke',
                               headers={'Authorization': 'Bearer owner-api-token'})
        assert response.status_code == 200
        with app.app_context():
            assert User.query.get(authed_user.id).api_token is None

    def test_unauthenticated_returns_401(self, client):
        with patch('app.auth.generate_auth_url', return_value='https://mock'):
            response = client.post('/token/revoke')
        assert response.status_code == 401
