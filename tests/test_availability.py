from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
from app.slots import compute_available_slots, to_google_utc

DATE = datetime(2024, 8, 1)
EARLY = datetime(2020, 1, 1, tzinfo=timezone.utc)


class TestComputeAvailableSlots:
    def test_no_members_returns_empty(self):
        assert compute_available_slots([], DATE, now=EARLY) == []

    def test_free_day_defaults_to_business_window(self):
        slots = compute_available_slots([[]], DATE, now=EARLY)
        assert len(slots) == 16
        assert slots[0] == {'start': '09:00', 'end': '09:30'}
        assert slots[-1] == {'start': '16:30', 'end': '17:00'}

    def test_explicit_window_overrides_default(self):
        slots = compute_available_slots([[]], DATE, window_start='22:00', window_end='23:30', now=EARLY)
        assert [s['start'] for s in slots] == ['22:00', '22:30', '23:00']

    def test_busy_period_excludes_overlapping_slots(self):
        busy = [{'start': '2024-08-01T11:00:00Z', 'end': '2024-08-01T12:00:00Z'}]
        slots = compute_available_slots([busy], DATE, now=EARLY)
        starts = [s['start'] for s in slots]
        assert '11:00' not in starts
        assert '11:30' not in starts
        assert '10:30' in starts
        assert '12:00' in starts

    def test_slot_free_if_any_member_free(self):
        busy_all_day = [{'start': '2024-08-01T00:00:00Z', 'end': '2024-08-02T00:00:00Z'}]
        slots = compute_available_slots([busy_all_day, []], DATE, now=EARLY)
        assert len(slots) == 16

    def test_labels_slots_in_local_timezone(self):
        slots = compute_available_slots([[]], DATE, tz='Asia/Tokyo', now=EARLY)
        assert len(slots) == 16
        assert slots[0] == {'start': '09:00', 'end': '09:30'}
        assert slots[-1] == {'start': '16:30', 'end': '17:00'}

    def test_busy_period_crossing_utc_midnight_blocks_correct_local_slot(self):
        # 2024-08-01 00:00 JST == 2024-07-31 15:00 UTC (JST = UTC+9)
        busy = [{'start': '2024-07-31T15:00:00Z', 'end': '2024-07-31T15:30:00Z'}]
        slots = compute_available_slots([busy], DATE, tz='Asia/Tokyo',
                                        window_start='00:00', window_end='01:00', now=EARLY)
        starts = [s['start'] for s in slots]
        assert '00:00' not in starts
        assert '00:30' in starts

    def test_excludes_slots_already_started_today(self):
        # now = 10:15 UTC on DATE: the 09:00, 09:30 and 10:00 slots have started; 10:30 is first offered
        mid_morning = datetime(DATE.year, DATE.month, DATE.day, 10, 15, tzinfo=timezone.utc)
        slots = compute_available_slots([[]], DATE, now=mid_morning)
        assert slots[0]['start'] == '10:30'

    def test_past_date_yields_no_slots(self):
        late = datetime(DATE.year, DATE.month, DATE.day, 23, 59, tzinfo=timezone.utc) + timedelta(days=1)
        assert compute_available_slots([[]], DATE, now=late) == []

    def test_now_comparison_uses_request_timezone(self):
        # 00:30 UTC == 09:30 JST: the 09:00 slot has started and 09:30 == now is not strictly after
        utc_now = datetime(DATE.year, DATE.month, DATE.day, 0, 30, tzinfo=timezone.utc)
        slots = compute_available_slots([[]], DATE, tz='Asia/Tokyo', now=utc_now)
        assert slots[0]['start'] == '10:00'


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
                                  query_string={'date': '2030-06-03'},
                                  headers=self.auth())
        assert response.status_code == 200
        assert len(response.json['slots']) == 16

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

    def test_returns_slots_labeled_in_local_timezone(self, client, authed_user, org_with_owner):
        with patch('app.org.routes.build', return_value=busy_service([])):
            response = client.get(f'/org/{org_with_owner}/availability',
                                  query_string={'date': '2030-06-03', 'tz': 'Asia/Tokyo'},
                                  headers=self.auth())
        assert response.status_code == 200
        assert len(response.json['slots']) == 16

    def test_unknown_timezone_returns_400(self, client, authed_user, org_with_owner):
        response = client.get(f'/org/{org_with_owner}/availability',
                              query_string={'date': '2024-08-01', 'tz': 'Not/AZone'},
                              headers=self.auth())
        assert response.status_code == 400
        assert 'Unknown timezone' in response.json['error']

    def test_passes_window_params_to_slot_generation(self, client, authed_user, org_with_owner):
        with patch('app.org.routes.build', return_value=busy_service([])):
            response = client.get(f'/org/{org_with_owner}/availability',
                                  query_string={'date': '2030-06-03',
                                                'window_start': '10:00', 'window_end': '12:00'},
                                  headers=self.auth())
        assert response.status_code == 200
        assert [s['start'] for s in response.json['slots']] == ['10:00', '10:30', '11:00', '11:30']

    def test_malformed_window_returns_400(self, client, authed_user, org_with_owner):
        response = client.get(f'/org/{org_with_owner}/availability',
                              query_string={'date': '2030-06-03', 'window_start': 'abc'},
                              headers=self.auth())
        assert response.status_code == 400
        assert 'Invalid booking window' in response.json['error']

    def test_inverted_window_returns_400(self, client, authed_user, org_with_owner):
        response = client.get(f'/org/{org_with_owner}/availability',
                              query_string={'date': '2030-06-03',
                                            'window_start': '17:00', 'window_end': '09:00'},
                              headers=self.auth())
        assert response.status_code == 400

    def test_queries_google_with_local_midnight_window_in_utc(self, client, authed_user, org_with_owner):
        service = busy_service([])
        with patch('app.org.routes.build', return_value=service):
            client.get(f'/org/{org_with_owner}/availability',
                      query_string={'date': '2030-06-03', 'tz': 'Asia/Tokyo'},
                      headers=self.auth())
        call_kwargs = service.freebusy().query.call_args[1]
        # freebusy still queries the full local day; the booking window only clamps slot generation
        assert call_kwargs['body']['timeMin'] == '2030-06-02T15:00:00Z'
        assert call_kwargs['body']['timeMax'] == '2030-06-03T15:00:00Z'


class TestToGoogleUtc:
    def test_naive_datetime_is_treated_as_already_utc(self):
        assert to_google_utc(datetime(2024, 8, 1, 11, 0)) == '2024-08-01T11:00:00Z'

    def test_aware_datetime_is_converted_to_utc(self):
        aware = datetime(2024, 8, 1, 11, 0, tzinfo=ZoneInfo('Asia/Tokyo'))
        assert to_google_utc(aware) == '2024-08-01T02:00:00Z'

    def test_utc_aware_datetime_passes_through(self):
        aware = datetime(2024, 8, 1, 11, 0, tzinfo=timezone.utc)
        assert to_google_utc(aware) == '2024-08-01T11:00:00Z'
