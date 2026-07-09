from unittest.mock import patch


def auth():
    return {'Authorization': 'Bearer owner-api-token'}


class TestOrgMe:
    def test_member_gets_own_org(self, client, authed_user, org_with_owner):
        response = client.get('/org/me', headers=auth())
        assert response.status_code == 200
        assert response.json['org_id'] == org_with_owner
        assert response.json['name'] == 'Test Org'
        assert response.json['calendar_id'] == 'org-cal-id'

    def test_user_without_org_returns_404(self, client, authed_user):
        response = client.get('/org/me', headers=auth())
        assert response.status_code == 404

    def test_unauthenticated_returns_401(self, client):
        with patch('app.auth.generate_auth_url', return_value='https://mock'):
            response = client.get('/org/me')
        assert response.status_code == 401
