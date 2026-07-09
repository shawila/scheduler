# scheduler

A Flask web app that integrates with Google Calendar via OAuth 2.0. Users connect their Google account, and the app stores their credentials to query busy hours on demand.

Also includes a standalone CLI script (`main.py`) that prints free 30-minute slots for any given day.

## Features

- Google OAuth 2.0 flow: connect a calendar with one redirect
- Stores per-user credentials in a local database (SQLite by default)
- `GET /get-busy-hours` returns calendar events for any date
- `app/slots.py` — pure, testable free-slot computation logic

## Prerequisites

- Python 3.9+
- A Google Cloud project with the **Google Calendar API** and **Google OAuth 2.0** enabled
- A `credentials.json` file downloaded from the Google Cloud Console (OAuth 2.0 Client ID, Desktop or Web type)

## Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd scheduler

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and set SECRET_KEY to a random string

# 5. Place your credentials.json in the project root (do not commit it)

# 6. Run database migrations
flask db upgrade

# 7. Start the server
python run.py
```

## Environment Variables

| Variable       | Default             | Description                                  |
|----------------|---------------------|----------------------------------------------|
| `FLASK_ENV`    | —                   | Set to `development` to allow HTTP for OAuth |
| `SECRET_KEY`   | `your-secret-key`   | Flask session secret — change before deploy  |
| `DATABASE_URL` | `sqlite:///app.db`  | SQLAlchemy connection string                 |

## API Endpoints

### `GET /`
Redirects the user to the Google OAuth consent screen.

### `GET /callback`
OAuth redirect target. Stores or updates the user's calendar credentials in the database.

### `GET /get-busy-hours`

Returns calendar events for a given user and date.

| Parameter | Required | Format       | Default |
|-----------|----------|--------------|---------|
| `email`   | yes      | string       | —       |
| `date`    | no       | `YYYY-MM-DD` | today   |

**Example:**
```
GET /get-busy-hours?email=user@example.com&date=2024-08-01
```

**Response:**
```json
[
  {"start": "2024-08-01T09:00:00Z", "end": "2024-08-01T10:00:00Z"},
  {"start": "2024-08-01T14:00:00Z", "end": "2024-08-01T15:30:00Z"}
]
```

### `POST /book`

Submits a booking request. Validates slot alignment, duration, store existence, and guest email domain before creating a pending booking. Sends a confirmation email to the guest.

| Field | Required | Description |
|---|---|---|
| `store_email` | yes | Must match a connected store in the system |
| `guest_email` | yes | Guest's email — domain is MX-validated |
| `guest_name` | yes | Guest's display name |
| `date` | yes | `YYYY-MM-DD` |
| `start_time` | yes | `HH:MM`, aligned to 30-minute slots (00 or 30) |
| `end_time` | yes | `HH:MM`, aligned to 30-minute slots (00 or 30) |

Rules: duration must be a multiple of 30 minutes and cannot exceed 3 hours.

**Example:**
```
POST /book
{
  "store_email": "store@example.com",
  "guest_email": "guest@example.com",
  "guest_name": "John Doe",
  "date": "2024-08-02",
  "start_time": "11:00",
  "end_time": "12:30"
}
```

**Response:** `200 {"message": "Confirmation email sent to guest@example.com"}`

---

### `GET /confirm-booking/<token>`

Confirms a pending booking. Creates a Google Calendar event on the store's calendar with the guest added as an attendee — Google sends the guest a native calendar invite.

- `404` if token is not found
- `410 Gone` if the confirmation link has expired (24-hour TTL)
- `200` with event details on success:

```json
{
  "event_id": "google_calendar_event_id",
  "title": "Appointment",
  "start": "2024-08-02T11:00:00Z",
  "end": "2024-08-02T12:30:00Z",
  "html_link": "https://calendar.google.com/event?eid=..."
}
```

## Standalone CLI

`main.py` authenticates via a local browser flow and prints free 30-minute slots for today:

```bash
python main.py
```

Credentials are cached in `token.pickle` (gitignored) for subsequent runs.

## Running Tests

```bash
python3 -m pytest tests/ -v
```

Tests cover `app/slots.py` (pure slot computation logic) and require no Google API credentials.

## Project Structure

```
scheduler/
├── app/
│   ├── __init__.py        # Flask app factory
│   ├── config.py          # Configuration from environment
│   ├── extensions.py      # SQLAlchemy instance
│   ├── slots.py           # Pure free-slot computation (testable, no Google deps)
│   └── main/
│       ├── __init__.py
│       └── routes.py      # OAuth flow and calendar endpoints
├── app/models/
│   └── customer.py        # Customer model (stores OAuth tokens)
├── migrations/            # Alembic migrations
├── tests/
│   └── test_scheduler.py  # Unit tests for slot logic
├── main.py                # Standalone CLI script
├── run.py                 # Flask app entry point
├── requirements.txt
└── .env.example
```
