from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SLOT_DURATION_MINUTES = 30
MAX_BOOKING_DURATION_MINUTES = 180


def compute_available_slots(members_busy: list, date: datetime, tz: str = 'UTC') -> list:
    """Slots where at least one member is free, labeled in `tz` wall time.
    members_busy holds one busy-period list ({'start','end'} UTC ISO strings,
    'Z'-suffixed) per member."""
    zone = ZoneInfo(tz)
    current = datetime(date.year, date.month, date.day, tzinfo=zone)
    day_end = current + timedelta(days=1)

    slots = []
    while current + timedelta(minutes=SLOT_DURATION_MINUTES) <= day_end:
        slot_end = current + timedelta(minutes=SLOT_DURATION_MINUTES)
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
