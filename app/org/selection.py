import random
from googleapiclient.discovery import build
from app.google_calendar import google_credentials_for


def select_admin(members, start_dt, end_dt, preferred_user_id=None):
    free_members = []
    for member in members:
        credentials = google_credentials_for(member.user)
        service = build('calendar', 'v3', credentials=credentials)
        freebusy = service.freebusy().query(body={
            'timeMin': start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'timeMax': end_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'timeZone': 'UTC',
            'items': [{'id': 'primary'}],
        }).execute()
        if not freebusy['calendars']['primary'].get('busy'):
            free_members.append(member)

    if not free_members:
        return None

    if preferred_user_id is not None:
        match = next((m for m in free_members if m.user_id == preferred_user_id), None)
        return match.user if match else None

    max_priority = max(m.priority for m in free_members)
    top_members = [m for m in free_members if m.priority == max_priority]
    return random.choice(top_members).user
