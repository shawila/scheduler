from unittest.mock import patch, MagicMock
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.extensions import db

OWNER_TOKEN = 'owner-api-token'


def auth(token=OWNER_TOKEN):
    return {'Authorization': f'Bearer {token}'}


def mock_cal_service(calendar_id='new-cal-id'):
    service = MagicMock()
    service.calendars.return_value.insert.return_value.execute.return_value = {'id': calendar_id}
    service.acl.return_value.insert.return_value.execute.return_value = {}
    return service


class TestPostOrgRegister:
    def test_unauthenticated_returns_401_with_auth_url(self, client):
        with patch('app.auth.generate_auth_url', return_value='https://accounts.google.com/mock'):
            response = client.post('/org/register', json={'org_name': 'Test'})
        assert response.status_code == 401
        assert 'auth_url' in response.json

    def test_missing_org_name_returns_400(self, client, authed_user):
        response = client.post('/org/register', json={}, headers=auth())
        assert response.status_code == 400
        assert 'org_name' in response.json['error']

    def test_already_in_org_returns_400(self, client, authed_user, org_with_owner):
        with patch('app.org.routes.build', return_value=mock_cal_service()):
            response = client.post('/org/register',
                                   json={'org_name': 'Another'},
                                   headers=auth())
        assert response.status_code == 400
        assert 'Already' in response.json['error']

    def test_valid_register_creates_org_and_owner_member(self, client, app, authed_user):
        with patch('app.org.routes.build', return_value=mock_cal_service('cal-abc')):
            response = client.post('/org/register',
                                   json={'org_name': 'My Org'},
                                   headers=auth())
        assert response.status_code == 201
        assert 'org_id' in response.json
        assert response.json['calendar_id'] == 'cal-abc'
        with app.app_context():
            org = Organization.query.first()
            assert org.name == 'My Org'
            assert org.google_calendar_id == 'cal-abc'
            member = OrganizationMember.query.filter_by(user_id=authed_user.id).first()
            assert member is not None
            assert member.role == 'owner'

    def test_valid_register_calls_google_calendar_api(self, client, authed_user):
        service = mock_cal_service()
        with patch('app.org.routes.build', return_value=service):
            client.post('/org/register', json={'org_name': 'My Org'}, headers=auth())
        service.calendars.return_value.insert.assert_called_once()
        # Creator already owns the calendar; a self-ACL grant is rejected by
        # Google ("Cannot change your own access level") and must be skipped.
        service.acl.return_value.insert.assert_not_called()
