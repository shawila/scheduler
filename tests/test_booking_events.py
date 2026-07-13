from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock
from app.booking.events import create_calendar_event


def make_org():
    org = MagicMock()
    org.google_calendar_id = 'org-cal-id'
    return org


def calendar_service():
    service = MagicMock()
    service.freebusy().query().execute.return_value = {'calendars': {'primary': {'busy': []}}}
    service.events().insert().execute.return_value = {
        'id': 'evt1', 'summary': 'Appointment — Jane', 'htmlLink': 'https://x',
        'start': {'dateTime': '2026-07-15T09:00:00', 'timeZone': 'Asia/Tokyo'},
        'end': {'dateTime': '2026-07-15T09:30:00', 'timeZone': 'Asia/Tokyo'},
    }
    # The setup call above (`service.events().insert()`) registers itself in
    # `call_args_list`; clear it so tests inspecting call_args_list only see
    # calls made by the code under test.
    service.events().insert.reset_mock()
    return service


class TestCreateCalendarEvent:
    def test_writes_local_wall_clock_and_zone_from_aware_datetimes(self):
        start = datetime(2026, 7, 15, 9, 0, tzinfo=ZoneInfo('Asia/Tokyo'))
        end = datetime(2026, 7, 15, 9, 30, tzinfo=ZoneInfo('Asia/Tokyo'))
        service = calendar_service()
        with patch('app.booking.events.build', return_value=service), \
             patch('app.booking.events.google_credentials_for', return_value=MagicMock()):
            create_calendar_event(MagicMock(), make_org(), 'g@example.com', 'Jane', start, end)
        body = service.events().insert.call_args_list[0][1]['body']
        assert body['start'] == {'dateTime': '2026-07-15T09:00:00', 'timeZone': 'Asia/Tokyo'}
        assert body['end'] == {'dateTime': '2026-07-15T09:30:00', 'timeZone': 'Asia/Tokyo'}

    def test_queries_freebusy_with_utc_instant(self):
        start = datetime(2026, 7, 15, 9, 0, tzinfo=ZoneInfo('Asia/Tokyo'))
        end = datetime(2026, 7, 15, 9, 30, tzinfo=ZoneInfo('Asia/Tokyo'))
        service = calendar_service()
        with patch('app.booking.events.build', return_value=service), \
             patch('app.booking.events.google_credentials_for', return_value=MagicMock()):
            create_calendar_event(MagicMock(), make_org(), 'g@example.com', 'Jane', start, end)
        call_kwargs = service.freebusy().query.call_args[1]
        # JST 09:00 == UTC 00:00 same day
        assert call_kwargs['body']['timeMin'] == '2026-07-15T00:00:00Z'
        assert call_kwargs['body']['timeMax'] == '2026-07-15T00:30:00Z'

    def test_naive_datetimes_default_to_utc_zone(self):
        start = datetime(2026, 7, 15, 9, 0)
        end = datetime(2026, 7, 15, 9, 30)
        service = calendar_service()
        with patch('app.booking.events.build', return_value=service), \
             patch('app.booking.events.google_credentials_for', return_value=MagicMock()):
            create_calendar_event(MagicMock(), make_org(), 'g@example.com', 'Jane', start, end)
        body = service.events().insert.call_args_list[0][1]['body']
        assert body['start']['timeZone'] == 'UTC'
