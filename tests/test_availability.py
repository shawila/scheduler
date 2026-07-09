from datetime import datetime
from unittest.mock import patch, MagicMock
from app.slots import compute_available_slots

DATE = datetime(2024, 8, 1)


class TestComputeAvailableSlots:
    def test_no_members_returns_empty(self):
        assert compute_available_slots([], DATE) == []

    def test_one_free_member_returns_all_48_slots(self):
        slots = compute_available_slots([[]], DATE)
        assert len(slots) == 48
        assert slots[0] == {'start': '00:00', 'end': '00:30'}
        assert slots[-1] == {'start': '23:30', 'end': '00:00'}

    def test_busy_period_excludes_overlapping_slots(self):
        busy = [{'start': '2024-08-01T11:00:00Z', 'end': '2024-08-01T12:00:00Z'}]
        slots = compute_available_slots([busy], DATE)
        starts = [s['start'] for s in slots]
        assert '11:00' not in starts
        assert '11:30' not in starts
        assert '10:30' in starts
        assert '12:00' in starts

    def test_slot_free_if_any_member_free(self):
        busy_all_day = [{'start': '2024-08-01T00:00:00Z', 'end': '2024-08-02T00:00:00Z'}]
        slots = compute_available_slots([busy_all_day, []], DATE)
        assert len(slots) == 48


def busy_service(busy):
    service = MagicMock()
    service.freebusy().query().execute.return_value = {
        'calendars': {'primary': {'busy': busy}}
    }
    return service


class TestAvailabilityEndpoint:
    def auth(self):
        return {'Authorization': 'Bearer owner-api-token'}

    def test_returns_slots(self, client, authed_user, org_with_owner):
        with patch('app.org.routes.build', return_value=busy_service([])):
            response = client.get(f'/org/{org_with_owner}/availability',
                                  query_string={'date': '2024-08-01'},
                                  headers=self.auth())
        assert response.status_code == 200
        assert len(response.json['slots']) == 48

    def test_invalid_date_returns_400(self, client, authed_user, org_with_owner):
        response = client.get(f'/org/{org_with_owner}/availability',
                              query_string={'date': 'nope'}, headers=self.auth())
        assert response.status_code == 400

    def test_non_member_returns_403(self, client, app, authed_user, org_with_owner):
        from app.extensions import db
        from app.models.user import User
        with app.app_context():
            outsider = User(
                email='outsider@example.com',
                token='t', refresh_token='r',
                token_uri='https://oauth2.googleapis.com/token',
                client_id='c', client_secret='s',
                scopes='https://www.googleapis.com/auth/calendar',
                api_token='outsider-token',
            )
            db.session.add(outsider)
            db.session.commit()
        response = client.get(f'/org/{org_with_owner}/availability',
                              query_string={'date': '2024-08-01'},
                              headers={'Authorization': 'Bearer outsider-token'})
        assert response.status_code == 403
