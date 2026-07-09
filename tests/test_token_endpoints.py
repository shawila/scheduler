from datetime import datetime, timedelta
from unittest.mock import patch
from app.extensions import db
from app.models.exchange_code import ExchangeCode
from app.models.user import User


def make_code(app, user_id, code='exchange-code-abc', expires_minutes=5):
    with app.app_context():
        row = ExchangeCode(
            code=code,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_minutes),
        )
        db.session.add(row)
        db.session.commit()


class TestTokenExchange:
    def test_valid_code_returns_api_token_and_email(self, client, app, authed_user):
        make_code(app, authed_user.id)
        response = client.post('/token/exchange', json={'code': 'exchange-code-abc'})
        assert response.status_code == 200
        assert response.json['api_token'] == 'owner-api-token'
        assert response.json['email'] == 'owner@example.com'

    def test_code_is_single_use(self, client, app, authed_user):
        make_code(app, authed_user.id)
        client.post('/token/exchange', json={'code': 'exchange-code-abc'})
        response = client.post('/token/exchange', json={'code': 'exchange-code-abc'})
        assert response.status_code == 401

    def test_expired_code_returns_401(self, client, app, authed_user):
        make_code(app, authed_user.id, code='old-code', expires_minutes=-1)
        response = client.post('/token/exchange', json={'code': 'old-code'})
        assert response.status_code == 401

    def test_unknown_code_returns_401(self, client):
        response = client.post('/token/exchange', json={'code': 'nope'})
        assert response.status_code == 401

    def test_missing_code_returns_401(self, client):
        response = client.post('/token/exchange', json={})
        assert response.status_code == 401


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
