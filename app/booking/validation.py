import os
from datetime import datetime, timezone
import dns.resolver
from app.slots import (SLOT_DURATION_MINUTES, MAX_BOOKING_DURATION_MINUTES,
                       DEFAULT_WINDOW_START, DEFAULT_WINDOW_END)


def is_slot_aligned(dt: datetime) -> bool:
    return dt.minute in (0, 30) and dt.second == 0


def validate_booking_duration(start: datetime, end: datetime) -> tuple:
    if end <= start:
        return False, 'End time must be after start time'
    duration_minutes = int((end - start).total_seconds() / 60)
    if duration_minutes % SLOT_DURATION_MINUTES != 0:
        return False, f'Duration must be a multiple of {SLOT_DURATION_MINUTES} minutes'
    if duration_minutes > MAX_BOOKING_DURATION_MINUTES:
        return False, f'Duration cannot exceed {MAX_BOOKING_DURATION_MINUTES} minutes'
    return True, ''


def check_mx_record(email: str) -> bool:
    if '@' not in email:
        return False
    domain = email.split('@')[-1]
    try:
        records = dns.resolver.resolve(domain, 'MX')
        return len(records) > 0
    except Exception:
        return False


def is_allowed_callback_url(url: str) -> bool:
    if not url.startswith('https://') and not url.startswith('http://'):
        return False
    allowed_prefix = os.environ.get('ALLOWED_CALLBACK_PREFIX')
    if allowed_prefix:
        return url.startswith(allowed_prefix)
    return True


def validate_within_window(start_dt: datetime, end_dt: datetime,
                           window_start: str, window_end: str,
                           now: datetime = None) -> tuple:
    try:
        ws = datetime.strptime(window_start, '%H:%M')
        we = datetime.strptime(window_end, '%H:%M')
    except ValueError:
        return False, 'Invalid booking window'
    if window_start >= window_end:
        return False, 'Invalid booking window'

    day_open = start_dt.replace(hour=ws.hour, minute=ws.minute, second=0, microsecond=0)
    day_close = start_dt.replace(hour=we.hour, minute=we.minute, second=0, microsecond=0)
    if start_dt < day_open or end_dt > day_close:
        return False, 'Requested time is outside booking hours'

    now = now or datetime.now(timezone.utc)
    if start_dt <= now.astimezone(start_dt.tzinfo):
        return False, 'Requested time is in the past'
    return True, ''
