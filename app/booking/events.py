from googleapiclient.discovery import build
from app.google_calendar import google_credentials_for


def create_calendar_event(admin, org, guest_email, guest_name, start_dt, end_dt):
    """Insert the event on the admin's primary calendar (guest invited) and
    mirror it on the org's shared calendar. Returns the created primary
    event, or None if the slot is busy."""
    credentials = google_credentials_for(admin)
    service = build('calendar', 'v3', credentials=credentials)

    freebusy = service.freebusy().query(body={
        'timeMin': start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'timeMax': end_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'timeZone': 'UTC',
        'items': [{'id': 'primary'}],
    }).execute()
    if freebusy['calendars']['primary'].get('busy'):
        return None

    event_body = {
        'summary': f'Appointment — {guest_name}',
        'start': {'dateTime': start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'), 'timeZone': 'UTC'},
        'end': {'dateTime': end_dt.strftime('%Y-%m-%dT%H:%M:%SZ'), 'timeZone': 'UTC'},
        'attendees': [{'email': guest_email, 'displayName': guest_name}],
    }
    created_event = service.events().insert(
        calendarId='primary',
        body=event_body,
        sendUpdates='all',
    ).execute()

    service.events().insert(
        calendarId=org.google_calendar_id,
        body={**event_body, 'attendees': []},
        sendUpdates='none',
    ).execute()

    return created_event
