from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
from app.org.selection import select_admin

START = datetime(2024, 8, 1, 11, 0, 0)
END = datetime(2024, 8, 1, 12, 0, 0)


def make_member(user_id, priority, busy=False):
    member = MagicMock()
    member.user_id = user_id
    member.priority = priority
    user = MagicMock()
    user.id = user_id
    member.user = user

    service = MagicMock()
    busy_slots = [{'start': 'x', 'end': 'y'}] if busy else []
    service.freebusy().query().execute.return_value = {
        'calendars': {'primary': {'busy': busy_slots}}
    }
    return member, service


class TestSelectAdmin:
    def test_returns_none_when_all_busy(self):
        m1, svc1 = make_member(1, priority=1, busy=True)
        m2, svc2 = make_member(2, priority=2, busy=True)
        with patch('app.org.selection.build', side_effect=[svc1, svc2]), \
             patch('app.org.selection.google_credentials_for', return_value=MagicMock()):
            result = select_admin([m1, m2], START, END)
        assert result is None

    def test_returns_free_admin(self):
        m1, svc1 = make_member(1, priority=1, busy=False)
        with patch('app.org.selection.build', return_value=svc1), \
             patch('app.org.selection.google_credentials_for', return_value=MagicMock()):
            result = select_admin([m1], START, END)
        assert result is m1.user

    def test_picks_highest_priority(self):
        m1, svc1 = make_member(1, priority=1, busy=False)
        m2, svc2 = make_member(2, priority=3, busy=False)
        with patch('app.org.selection.build', side_effect=[svc1, svc2]), \
             patch('app.org.selection.google_credentials_for', return_value=MagicMock()):
            result = select_admin([m1, m2], START, END)
        assert result is m2.user

    def test_random_on_priority_tie(self):
        m1, svc1 = make_member(1, priority=2, busy=False)
        m2, svc2 = make_member(2, priority=2, busy=False)
        results = set()
        for _ in range(20):
            with patch('app.org.selection.build', side_effect=[svc1, svc2]), \
                 patch('app.org.selection.google_credentials_for', return_value=MagicMock()):
                result = select_admin([m1, m2], START, END)
                results.add(result.id)
        assert len(results) == 2

    def test_preferred_user_free_returns_them(self):
        m1, svc1 = make_member(1, priority=5, busy=False)
        m2, svc2 = make_member(2, priority=1, busy=False)
        with patch('app.org.selection.build', side_effect=[svc1, svc2]), \
             patch('app.org.selection.google_credentials_for', return_value=MagicMock()):
            result = select_admin([m1, m2], START, END, preferred_user_id=2)
        assert result.id == 2

    def test_preferred_user_busy_returns_none(self):
        m1, svc1 = make_member(1, priority=5, busy=False)
        m2, svc2 = make_member(2, priority=1, busy=True)
        with patch('app.org.selection.build', side_effect=[svc1, svc2]), \
             patch('app.org.selection.google_credentials_for', return_value=MagicMock()):
            result = select_admin([m1, m2], START, END, preferred_user_id=2)
        assert result is None


class TestSelectAdminTimezone:
    def test_converts_aware_local_datetimes_to_utc_instant(self):
        start = datetime(2024, 8, 1, 0, 0, tzinfo=ZoneInfo('Asia/Tokyo'))
        end = datetime(2024, 8, 1, 0, 30, tzinfo=ZoneInfo('Asia/Tokyo'))
        m1, svc1 = make_member(1, priority=1, busy=False)
        with patch('app.org.selection.build', return_value=svc1), \
             patch('app.org.selection.google_credentials_for', return_value=MagicMock()):
            select_admin([m1], start, end)
        call_kwargs = svc1.freebusy().query.call_args[1]
        assert call_kwargs['body']['timeMin'] == '2024-07-31T15:00:00Z'
        assert call_kwargs['body']['timeMax'] == '2024-07-31T15:30:00Z'
