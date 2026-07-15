import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from app.extensions import db
from app.models.pending_booking import PendingBooking
from app.models.booking import Booking

OWNER_TOKEN = 'owner-api-token'

VALID_PAYLOAD = {
    'org_uid': 1,
    'guest_email': 'guest@example.com',
    'guest_name': 'John Doe',
    'date': '2024-08-01',
    'start_time': '11:00',
    'end_time': '12:30',
}


def auth(token=OWNER_TOKEN):
    return {'Authorization': f'Bearer {token}'}


def mock_free_service():
    service = MagicMock()
    service.freebusy().query().execute.return_value = {
        'calendars': {'primary': {'busy': []}}
    }
    return service


class TestPostBook:
    def test_unauthenticated_returns_401(self, client):
        with patch('app.auth.generate_auth_url', return_value='https://mock'):
            response = client.post('/book', json=VALID_PAYLOAD)
        assert response.status_code == 401

    def test_missing_fields_returns_400(self, client, authed_user, org_with_owner):
        response = client.post('/book',
                               json={'org_uid': org_with_owner},
                               headers=auth())
        assert response.status_code == 400
        assert 'Missing' in response.json['error']

    def test_invalid_date_format_returns_400(self, client, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner, 'date': 'not-a-date'}
        response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 400

    def test_unaligned_start_time_returns_400(self, client, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner, 'start_time': '11:15'}
        response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 400
        assert 'aligned' in response.json['error']

    def test_unaligned_end_time_returns_400(self, client, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner,
                   'start_time': '11:00', 'end_time': '11:45'}
        response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 400
        assert 'aligned' in response.json['error']

    def test_duration_exceeding_max_returns_400(self, client, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner,
                   'start_time': '11:00', 'end_time': '14:30'}
        response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 400
        assert '180' in response.json['error']

    def test_end_before_start_returns_400(self, client, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner,
                   'start_time': '12:00', 'end_time': '11:00'}
        response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 400

    def test_org_not_found_returns_400(self, client, authed_user):
        payload = {**VALID_PAYLOAD, 'org_uid': 99999}
        response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 400
        assert 'Organization not found' in response.json['error']

    def test_mx_check_failure_returns_400(self, client, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner}
        with patch('app.booking.routes.check_mx_record', return_value=False):
            response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 400
        assert 'email domain' in response.json['error']

    def test_all_admins_busy_returns_409(self, client, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner}
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=None):
            response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 409

    def test_valid_request_creates_pending_booking(self, client, app, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner}
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=authed_user), \
             patch('app.booking.routes.send_confirmation_email') as mock_email:
            response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 201
        assert 'guest@example.com' in response.json['message']
        mock_email.assert_called_once()
        with app.app_context():
            pending = PendingBooking.query.filter_by(guest_email='guest@example.com').first()
            assert pending is not None
            assert pending.admin_user_id == authed_user.id
            assert pending.org_id == org_with_owner

    def test_stores_callback_url_when_provided(self, client, app, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner, 'callback_url': 'https://hatan.test/api/scheduler/bookings/callback?ref=abc'}
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=authed_user), \
             patch('app.booking.routes.send_confirmation_email'):
            response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 201
        with app.app_context():
            pending = PendingBooking.query.filter_by(guest_email='guest@example.com').first()
            assert pending.callback_url == 'https://hatan.test/api/scheduler/bookings/callback?ref=abc'

    def test_callback_url_defaults_to_none(self, client, app, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner}
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=authed_user), \
             patch('app.booking.routes.send_confirmation_email'):
            client.post('/book', json=payload, headers=auth())
        with app.app_context():
            pending = PendingBooking.query.filter_by(guest_email='guest@example.com').first()
            assert pending.callback_url is None


def make_pending(app, org_id, admin_user_id, token='valid-token-abc', expires_hours=24):
    with app.app_context():
        pending = PendingBooking(
            confirmation_token=token,
            org_id=org_id,
            admin_user_id=admin_user_id,
            guest_email='guest@example.com',
            guest_name='John Doe',
            start_datetime=datetime(2024, 8, 1, 11, 0, 0),
            end_datetime=datetime(2024, 8, 1, 12, 30, 0),
            expires_at=datetime.utcnow() + timedelta(hours=expires_hours),
        )
        db.session.add(pending)
        db.session.commit()


def mock_calendar_service(event_id='google_event_123'):
    service = MagicMock()
    service.freebusy.return_value.query.return_value.execute.return_value = {
        'calendars': {'primary': {'busy': []}}
    }
    service.events.return_value.insert.return_value.execute.return_value = {
        'id': event_id,
        'summary': 'Appointment',
        'start': {'dateTime': '2024-08-01T11:00:00Z'},
        'end': {'dateTime': '2024-08-01T12:30:00Z'},
        'htmlLink': 'https://calendar.google.com/event?eid=abc',
    }
    return service


class TestConfirmBooking:
    def test_unknown_token_returns_404(self, client, authed_user, org_with_owner):
        response = client.get('/confirm-booking/nonexistent-token')
        assert response.status_code == 404

    def test_expired_token_returns_410(self, client, app, authed_user, org_with_owner):
        make_pending(app, org_with_owner, authed_user.id, token='expired-token', expires_hours=-1)
        response = client.get('/confirm-booking/expired-token')
        assert response.status_code == 410

    def test_valid_token_returns_200_with_event_details(self, client, app, authed_user, org_with_owner):
        make_pending(app, org_with_owner, authed_user.id)
        with patch('app.booking.events.build', return_value=mock_calendar_service()):
            response = client.get('/confirm-booking/valid-token-abc')
        assert response.status_code == 200
        assert response.json['event_id'] == 'google_event_123'
        assert 'html_link' in response.json

    def test_valid_token_saves_booking_record(self, client, app, authed_user, org_with_owner):
        make_pending(app, org_with_owner, authed_user.id)
        with patch('app.booking.events.build', return_value=mock_calendar_service()):
            client.get('/confirm-booking/valid-token-abc')
        with app.app_context():
            booking = Booking.query.filter_by(guest_email='guest@example.com').first()
            assert booking is not None
            assert booking.google_event_id == 'google_event_123'
            assert booking.org_id == org_with_owner

    def test_valid_token_deletes_pending_booking(self, client, app, authed_user, org_with_owner):
        make_pending(app, org_with_owner, authed_user.id)
        with patch('app.booking.events.build', return_value=mock_calendar_service()):
            client.get('/confirm-booking/valid-token-abc')
        with app.app_context():
            assert PendingBooking.query.filter_by(confirmation_token='valid-token-abc').first() is None

    def test_admin_not_found_returns_400(self, client, app, org_with_owner):
        with app.app_context():
            pending = PendingBooking(
                confirmation_token='orphan-token',
                org_id=org_with_owner,
                admin_user_id=99999,
                guest_email='guest@example.com',
                guest_name='John Doe',
                start_datetime=datetime(2024, 8, 1, 11, 0, 0),
                end_datetime=datetime(2024, 8, 1, 12, 30, 0),
                expires_at=datetime.utcnow() + timedelta(hours=24),
            )
            db.session.add(pending)
            db.session.commit()
        response = client.get('/confirm-booking/orphan-token')
        assert response.status_code == 400
        assert 'Admin account not found' in response.json['error']

    def test_slot_taken_at_confirmation_returns_409(self, client, app, authed_user, org_with_owner):
        make_pending(app, org_with_owner, authed_user.id)
        busy_service = MagicMock()
        busy_service.freebusy().query().execute.return_value = {
            'calendars': {'primary': {'busy': [
                {'start': '2024-08-01T11:00:00Z', 'end': '2024-08-01T12:30:00Z'}
            ]}}
        }
        with patch('app.booking.events.build', return_value=busy_service):
            response = client.get('/confirm-booking/valid-token-abc')
        assert response.status_code == 409

    def test_event_written_to_admin_and_org_calendar(self, client, app, authed_user, org_with_owner):
        make_pending(app, org_with_owner, authed_user.id)
        service = mock_calendar_service()
        with patch('app.booking.events.build', return_value=service):
            client.get('/confirm-booking/valid-token-abc')
        # First insert: admin personal calendar (sendUpdates='all')
        first_call_kwargs = service.events().insert.call_args_list[0][1]
        assert any(a['email'] == 'guest@example.com'
                   for a in first_call_kwargs['body']['attendees'])
        assert first_call_kwargs['sendUpdates'] == 'all'
        # Second insert: org shared calendar (sendUpdates='none')
        second_call_kwargs = service.events().insert.call_args_list[1][1]
        assert second_call_kwargs['calendarId'] == 'org-cal-id'
        assert second_call_kwargs['sendUpdates'] == 'none'

    def test_event_summary_includes_guest_name(self, client, app, authed_user, org_with_owner):
        make_pending(app, org_with_owner, authed_user.id)
        service = mock_calendar_service()
        with patch('app.booking.events.build', return_value=service):
            client.get('/confirm-booking/valid-token-abc')
        body = service.events().insert.call_args_list[0][1]['body']
        assert body['summary'] == 'Appointment — John Doe'


CONFIRMED_EVENT = {
    'id': 'google_event_direct',
    'summary': 'Appointment',
    'start': {'dateTime': '2024-08-01T11:00:00Z'},
    'end': {'dateTime': '2024-08-01T12:30:00Z'},
    'htmlLink': 'https://calendar.google.com/event?eid=direct',
}


class TestPostBookConfirmed:
    def _payload(self, org_id):
        return {**VALID_PAYLOAD, 'org_uid': org_id, 'confirmed': True}

    def test_creates_event_immediately(self, client, app, authed_user, org_with_owner):
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=authed_user), \
             patch('app.booking.routes.create_calendar_event', return_value=CONFIRMED_EVENT), \
             patch('app.booking.routes.send_confirmation_email') as mock_email:
            response = client.post('/book', json=self._payload(org_with_owner), headers=auth())
        assert response.status_code == 201
        assert response.json['event_id'] == 'google_event_direct'
        mock_email.assert_not_called()
        with app.app_context():
            assert Booking.query.filter_by(google_event_id='google_event_direct').first() is not None
            assert PendingBooking.query.filter_by(guest_email='guest@example.com').first() is None

    def test_slot_taken_returns_409(self, client, app, authed_user, org_with_owner):
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=authed_user), \
             patch('app.booking.routes.create_calendar_event', return_value=None):
            response = client.post('/book', json=self._payload(org_with_owner), headers=auth())
        assert response.status_code == 409
        with app.app_context():
            assert Booking.query.count() == 0


class TestPostBookConfirmedTimezone:
    def _payload(self, org_id, tz='Asia/Tokyo'):
        return {**VALID_PAYLOAD, 'org_uid': org_id, 'tz': tz, 'confirmed': True}

    def test_passes_local_aware_datetimes_and_stores_utc(self, client, app, authed_user, org_with_owner):
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=authed_user), \
             patch('app.booking.routes.create_calendar_event', return_value=CONFIRMED_EVENT) as mock_event, \
             patch('app.booking.routes.send_confirmation_email'):
            response = client.post('/book', json=self._payload(org_with_owner), headers=auth())
        assert response.status_code == 201

        start_dt = mock_event.call_args[0][4]
        assert start_dt.tzinfo.key == 'Asia/Tokyo'
        assert start_dt.hour == 11  # VALID_PAYLOAD start_time, local wall time

        with app.app_context():
            booking = Booking.query.filter_by(google_event_id='google_event_direct').first()
            # 11:00 JST == 02:00 UTC same day
            assert booking.start_datetime == datetime(2024, 8, 1, 2, 0)

    def test_unknown_timezone_returns_400(self, client, authed_user, org_with_owner):
        response = client.post('/book', json=self._payload(org_with_owner, tz='Not/AZone'), headers=auth())
        assert response.status_code == 400
        assert 'Unknown timezone' in response.json['error']


class TestPostBookPendingTimezone:
    def test_stores_requested_timezone_and_utc_instant(self, client, app, authed_user, org_with_owner):
        payload = {**VALID_PAYLOAD, 'org_uid': org_with_owner, 'tz': 'Asia/Tokyo'}
        with patch('app.booking.routes.check_mx_record', return_value=True), \
             patch('app.booking.routes.select_admin', return_value=authed_user), \
             patch('app.booking.routes.send_confirmation_email'):
            response = client.post('/book', json=payload, headers=auth())
        assert response.status_code == 201
        with app.app_context():
            pending = PendingBooking.query.filter_by(guest_email='guest@example.com').first()
            assert pending.time_zone == 'Asia/Tokyo'
            assert pending.start_datetime == datetime(2024, 8, 1, 2, 0)


class TestConfirmBookingTimezone:
    def test_confirms_using_the_pending_timezone(self, client, app, authed_user, org_with_owner):
        with app.app_context():
            pending = PendingBooking(
                confirmation_token='tz-token',
                org_id=org_with_owner,
                admin_user_id=authed_user.id,
                guest_email='guest@example.com',
                guest_name='John Doe',
                start_datetime=datetime(2024, 8, 1, 2, 0),   # UTC; == 11:00 JST
                end_datetime=datetime(2024, 8, 1, 3, 30),    # UTC; == 12:30 JST
                time_zone='Asia/Tokyo',
                expires_at=datetime.utcnow() + timedelta(hours=24),
            )
            db.session.add(pending)
            db.session.commit()

        with patch('app.booking.routes.create_calendar_event', return_value=CONFIRMED_EVENT) as mock_event:
            response = client.get('/confirm-booking/tz-token')
        assert response.status_code == 200

        start_dt = mock_event.call_args[0][4]
        assert start_dt.tzinfo.key == 'Asia/Tokyo'
        assert start_dt.hour == 11
