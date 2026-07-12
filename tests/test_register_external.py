from unittest.mock import patch, MagicMock
from app.extensions import db
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User

HEADERS = {'X-Service-Token': 'service-secret'}
PAYLOAD = {'org_name': 'Acme', 'pps_user_id': 'uuid-1', 'email': 'admin@example.com'}


def calendar_service(calendar_id='new-cal@group'):
    service = MagicMock()
    service.calendars().insert().execute.return_value = {'id': calendar_id}
    return service


class TestRegisterExternal:
    def _post(self, client, payload=None, headers=None):
        return client.post('/org/register-external',
                           json=payload or PAYLOAD,
                           headers=headers if headers is not None else HEADERS)

    def test_missing_service_token_returns_401(self, client, monkeypatch):
        monkeypatch.setenv('HATAN_SERVICE_TOKEN', 'service-secret')
        resp = self._post(client, headers={})
        assert resp.status_code == 401

    def test_wrong_service_token_returns_401(self, client, monkeypatch):
        monkeypatch.setenv('HATAN_SERVICE_TOKEN', 'service-secret')
        resp = self._post(client, headers={'X-Service-Token': 'nope'})
        assert resp.status_code == 401

    def test_unset_env_returns_401(self, client, monkeypatch):
        monkeypatch.delenv('HATAN_SERVICE_TOKEN', raising=False)
        resp = self._post(client)
        assert resp.status_code == 401

    def test_missing_fields_returns_400(self, client, monkeypatch):
        monkeypatch.setenv('HATAN_SERVICE_TOKEN', 'service-secret')
        resp = self._post(client, payload={'org_name': 'Acme'})
        assert resp.status_code == 400

    def test_creates_shell_user_org_and_calendar(self, client, app, monkeypatch):
        monkeypatch.setenv('HATAN_SERVICE_TOKEN', 'service-secret')
        with patch('app.org.routes.google_credentials_for', return_value=MagicMock()), \
             patch('app.org.routes.build', return_value=calendar_service()):
            resp = self._post(client)
        assert resp.status_code == 201
        assert resp.json['calendar_id'] == 'new-cal@group'
        assert resp.json['api_token']
        with app.app_context():
            user = User.query.filter_by(pps_user_id='uuid-1').first()
            assert user.email == 'admin@example.com'
            assert user.token is None
            org = Organization.query.get(resp.json['org_id'])
            assert org.google_calendar_id == 'new-cal@group'
            member = OrganizationMember.query.filter_by(user_id=user.id).first()
            assert member.role == 'owner'

    def test_reconnect_returns_existing_org_with_new_token(self, client, app, monkeypatch):
        monkeypatch.setenv('HATAN_SERVICE_TOKEN', 'service-secret')
        with app.app_context():
            user = User(email='admin@example.com', pps_user_id='uuid-1', api_token='old-token')
            db.session.add(user)
            db.session.flush()
            org = Organization(name='Acme', google_calendar_id='existing-cal@group')
            db.session.add(org)
            db.session.flush()
            db.session.add(OrganizationMember(org_id=org.id, user_id=user.id, role='owner', priority=1))
            db.session.commit()
            existing_org_id = org.id

        resp = self._post(client)
        assert resp.status_code == 200
        assert resp.json['org_id'] == existing_org_id
        assert resp.json['calendar_id'] == 'existing-cal@group'
        assert resp.json['api_token'] != 'old-token'

    def test_attaches_pps_user_id_to_existing_email_user(self, client, app, store, monkeypatch):
        monkeypatch.setenv('HATAN_SERVICE_TOKEN', 'service-secret')
        payload = {**PAYLOAD, 'email': 'store@example.com'}
        with patch('app.org.routes.google_credentials_for', return_value=MagicMock()), \
             patch('app.org.routes.build', return_value=calendar_service()):
            resp = self._post(client, payload=payload)
        assert resp.status_code == 201
        with app.app_context():
            assert User.query.filter_by(email='store@example.com').first().pps_user_id == 'uuid-1'

    def test_skips_acl_grant_when_creator_is_owner(self, client, monkeypatch):
        monkeypatch.setenv('HATAN_SERVICE_TOKEN', 'service-secret')
        service = calendar_service()
        with patch('app.org.routes.google_credentials_for', return_value=MagicMock()), \
             patch('app.org.routes.build', return_value=service):
            resp = self._post(client)
        assert resp.status_code == 201
        service.acl().insert.assert_not_called()
