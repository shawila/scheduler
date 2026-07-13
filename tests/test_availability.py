from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
from app.slots import compute_available_slots, to_google_utc

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

    def test_labels_slots_in_local_timezone(self):
        slots = compute_available_slots([[]], DATE, tz='Asia/Tokyo')
        assert len(slots) == 48
        assert slots[0] == {'start': '00:00', 'end': '00:30'}
        assert slots[-1] == {'start': '23:30', 'end': '00:00'}

    def test_busy_period_crossing_utc_midnight_blocks_correct_local_slot(self):
        # 2024-08-01 00:00 JST == 2024-07-31 15:00 UTC (JST = UTC+9)
        busy = [{'start': '2024-07-31T15:00:00Z', 'end': '2024-07-31T15:30:00Z'}]
        slots = compute_available_slots([busy], DATE, tz='Asia/Tokyo')
        starts = [s['start'] for s in slots]
        assert '00:00' not in starts
        assert '00:30' in starts


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


class TestToGoogleUtc:
    def test_naive_datetime_is_treated_as_already_utc(self):
        assert to_google_utc(datetime(2024, 8, 1, 11, 0)) == '2024-08-01T11:00:00Z'

    def test_aware_datetime_is_converted_to_utc(self):
        aware = datetime(2024, 8, 1, 11, 0, tzinfo=ZoneInfo('Asia/Tokyo'))
        assert to_google_utc(aware) == '2024-08-01T02:00:00Z'

    def test_utc_aware_datetime_passes_through(self):
        aware = datetime(2024, 8, 1, 11, 0, tzinfo=timezone.utc)
        assert to_google_utc(aware) == '2024-08-01T11:00:00Z'
