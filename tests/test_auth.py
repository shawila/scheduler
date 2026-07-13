from unittest.mock import patch
from app.models.user import User
from app.extensions import db


def test_index_route_removed(client):
    response = client.get('/')
    assert response.status_code == 404


class TestRequireAuth:
    def test_missing_token_returns_401_with_auth_url(self, client):
        with patch('app.auth.generate_auth_url', return_value='https://accounts.google.com/mock'):
            response = client.post('/token/revoke')
        assert response.status_code == 401
        assert 'auth_url' in response.json
        assert response.json['auth_url'] == 'https://accounts.google.com/mock'

    def test_invalid_token_returns_401(self, client):
        with patch('app.auth.generate_auth_url', return_value='https://mock'):
            response = client.post(
                '/token/revoke',
                headers={'Authorization': 'Bearer invalid-token'},
            )
        assert response.status_code == 401

    def test_valid_token_passes_through(self, client, app):
        with app.app_context():
            user = User(
                email='auth@example.com', token='t', refresh_token='r',
                token_uri='u', client_id='c', client_secret='s', scopes='sc',
                api_token='valid-token',
            )
            db.session.add(user)
            db.session.commit()
        response = client.post(
            '/token/revoke',
            headers={'Authorization': 'Bearer valid-token'},
        )
        assert response.status_code == 200
