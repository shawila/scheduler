from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SLOT_DURATION_MINUTES = 30
MAX_BOOKING_DURATION_MINUTES = 180
DEFAULT_WINDOW_START = '09:00'
DEFAULT_WINDOW_END = '17:00'


def _parse_hhmm(value: str) -> tuple:
    parsed = datetime.strptime(value, '%H:%M')
    return parsed.hour, parsed.minute


def is_valid_window(window_start: str, window_end: str) -> bool:
    """True when both bounds parse as HH:MM and start is before end,
    compared numerically (string comparison breaks on non-zero-padded input)."""
    try:
        ws = _parse_hhmm(window_start)
        we = _parse_hhmm(window_end)
    except (ValueError, TypeError):
        return False
    return ws < we


def compute_available_slots(members_busy: list, date: datetime, tz: str = 'UTC',
                            window_start: str = DEFAULT_WINDOW_START,
                            window_end: str = DEFAULT_WINDOW_END,
                            now: datetime = None) -> list:
    """Slots where at least one member is free, labeled in `tz` wall time,
    clamped to the [window_start, window_end) org-local window. Slots whose
    start is not strictly after `now` are excluded (past dates yield []).
    members_busy holds one busy-period list ({'start','end'} UTC ISO strings,
    'Z'-suffixed) per member."""
    zone = ZoneInfo(tz)
    ws_hour, ws_minute = _parse_hhmm(window_start)
    we_hour, we_minute = _parse_hhmm(window_end)
    day = datetime(date.year, date.month, date.day, tzinfo=zone)
    current = day.replace(hour=ws_hour, minute=ws_minute)
    window_close = day.replace(hour=we_hour, minute=we_minute)
    now_local = (now or datetime.now(timezone.utc)).astimezone(zone)

    slots = []
    while current + timedelta(minutes=SLOT_DURATION_MINUTES) <= window_close:
        slot_end = current + timedelta(minutes=SLOT_DURATION_MINUTES)
        if current > now_local:
            for busy_list in members_busy:
                if all(not _overlaps(current, slot_end, busy) for busy in busy_list):
                    slots.append({
                        'start': current.strftime('%H:%M'),
                        'end': slot_end.strftime('%H:%M'),
                    })
                    break
        current = slot_end

    return slots


def _overlaps(slot_start, slot_end, busy):
    busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
    busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
    return slot_start < busy_end and slot_end > busy_start


def to_google_utc(dt: datetime) -> str:
    """Format a datetime as a Google Calendar RFC3339 UTC instant
    ('...Z'). Naive datetimes are treated as already-UTC (legacy callers);
    aware datetimes are converted from their own zone."""
    if dt.tzinfo is None:
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
