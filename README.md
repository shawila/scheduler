# scheduler

A Flask API that connects organizations' Google Calendars for booking scheduling. It is
the backend booking service consumed by [hatan](../hatan) — it manages Google OAuth
credentials, organization/member records, and availability/booking logic against
Google Calendar.

## Features

- Broker-backed Google Calendar access via `pps_auth`, plus a direct-OAuth invite/join flow
  for adding org members
- Organizations with prioritized members; bookings are routed to the best-available member
- Merged free/busy availability across all members of an organization, in any IANA timezone
- Direct (`confirmed: true`) or email-confirmed (pending → confirmation link) booking creation
- Google Calendar events are created directly on the org's shared calendar

## Prerequisites

- Python 3.9+
- A Google Cloud project with the **Google Calendar API** and **Google OAuth 2.0** enabled
- A Google OAuth 2.0 Client ID (Web type) — its client ID/secret are supplied via
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` env vars, not a downloaded file

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
# Edit .env and set SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

# 5. Run database migrations
flask db upgrade

# 6. Start the server (dev listens on http://127.0.0.1:3032)
python run.py
```

## Environment Variables

| Variable                     | Default                  | Description                                                       |
|-------------------------------|---------------------------|---------------------------------------------------------------------|
| `FLASK_ENV`                   | —                          | Set to `development` to allow HTTP for OAuth                       |
| `SECRET_KEY`                  | `your-secret-key`          | Flask session secret — change before deploy                        |
| `DATABASE_URL`                | `sqlite:///app.db`         | SQLAlchemy connection string. When this is a Postgres URL, scheduler's tables are automatically isolated in the `scheduler` schema (`search_path` set on the connection; the schema is created via `CREATE SCHEMA IF NOT EXISTS` on `flask db upgrade` if needed) — no separate config required |
| `PORT`                        | `3032`                     | Dev server port (`python run.py` only — production gunicorn stays on 5000) |
| `MAIL_SERVER`                 | `smtp.gmail.com`           | SMTP server for confirmation/invite emails                          |
| `MAIL_PORT`                   | `587`                      | SMTP port                                                           |
| `MAIL_USERNAME`               | —                          | SMTP username / default sender                                     |
| `MAIL_PASSWORD`               | —                          | SMTP password                                                      |
| `BOOKING_CONFIRM_BASE_URL`    | `http://localhost:5000`    | Base URL used to build confirmation/invite links in emails          |
| `GOOGLE_CLIENT_ID`            | —                          | Google OAuth 2.0 client id (Web type) — used by the direct-OAuth invite/join flow and the 401 `auth_url` |
| `GOOGLE_CLIENT_SECRET`        | —                          | Google OAuth 2.0 client secret — pair of `GOOGLE_CLIENT_ID`         |
| `PPS_AUTH_BASE_URL`           | `http://localhost:4000`    | `pps_auth` base URL for Google token exchange                       |
| `SCHEDULER_PPS_CLIENT_ID`     | `scheduler`                | `pps_auth` client id for the exchange                               |
| `SCHEDULER_PPS_CLIENT_SECRET` | —                          | `pps_auth` client secret (from `cargo run --bin seed`)              |
| `HATAN_SERVICE_TOKEN`         | —                          | Shared secret for `/org/register-external` (same value in hatan)    |

For production, use `postgresql://user:pass@host:5432/dbname` for `DATABASE_URL`. If that
database is shared with sibling apps (e.g. hatan), no separate database is needed —
scheduler's tables and its own `alembic_version` live in the dedicated `scheduler` schema
(see above), isolated from the other apps' tables.

## Data Model

| Model                | Purpose                                                                 |
|-----------------------|--------------------------------------------------------------------------|
| `User`                | A person with Google Calendar access — either legacy direct-OAuth (`token`/`refresh_token`, populated only via the invite/join flow) or broker-backed (`pps_user_id`, tokens fetched from `pps_auth`) |
| `Organization`        | An org with its own Google Calendar (`google_calendar_id`)               |
| `OrganizationMember`  | Links a `User` to an `Organization` with a `role` (`owner`/`manager`/`employee`) and booking `priority` |
| `OrganizationInvite`  | A pending invite for a new member to join an org via direct OAuth        |
| `Booking`             | A confirmed booking, mirrors a Google Calendar event                     |
| `PendingBooking`      | An unconfirmed booking awaiting guest confirmation via emailed link       |

> Note: the invite/join flow still has no caller in hatan (confirmed 2026-07-13) — see
> `docs/BACKLOG.md`. It is unscheduled scaffolding, not a removal candidate. The
> pending-booking/email-confirmation flow **is now wired up**: hatan's chat-widget booking
> (`Api::Widget::BookingsController`) calls `POST /book` with `confirmed: false` and a
> `callback_url`, and `GET /confirm-booking/<token>` notifies that URL when the guest
> confirms (confirmed live 2026-09-28).

## API Endpoints

### Auth (`app/main`)

| Route | Method | Description |
|---|---|---|
| `/token/revoke` | POST (Bearer) | Clears the caller's `api_token` |

### Booking (`app/booking`)

| Route | Method | Description |
|---|---|---|
| `/book` | POST (Bearer) | Creates a booking. Validates slot alignment (30-min), duration (≤3h), org existence, and guest email domain (MX). Picks an available org member. `confirmed: true` creates the Google Calendar event immediately; otherwise a `PendingBooking` is stored and a confirmation email is sent. |
| `/confirm-booking/<token>` | GET | Confirms a pending booking — creates the Google Calendar event and a `Booking` record, deletes the `PendingBooking` |

`POST /book` body:

| Field | Required | Description |
|---|---|---|
| `org_uid` | yes | Organization id |
| `guest_email` | yes | Guest's email — domain is MX-validated |
| `guest_name` | yes | Guest's display name |
| `date` | yes | `YYYY-MM-DD` |
| `start_time` / `end_time` | yes | `HH:MM`, aligned to 30-minute slots |
| `tz` | no (default `UTC`) | IANA timezone for `start_time`/`end_time` |
| `user_id` | no | Preferred member id to book, if available |
| `confirmed` | no (default `false`) | Skip the email-confirmation step and book immediately |

### Organizations (`app/org`, prefix `/org`)

| Route | Method | Description |
|---|---|---|
| `/org/me` | GET (Bearer) | Returns the caller's organization |
| `/org/<org_uid>/availability` | GET (Bearer) | Merged free-slot availability across all org members for a given `date` and `tz` |
| `/org/register-external` | POST (`X-Service-Token`) | Service-authenticated org/user registration for hatan — creates or looks up a broker-backed (`pps_user_id`) user and their org |
| `/org/<org_uid>/invite` | POST (Bearer) | Manager/owner invites a new member by email |
| `/org/<org_uid>/join/<token>` | GET | Invitee accepts an invite — starts direct Google OAuth |
| `/org/join-callback` | GET | OAuth redirect target for the invite flow — creates the `OrganizationMember` |
| `/org/<org_uid>/users/<user_id>` | PUT (Bearer) | Manager/owner updates a member's `role`/`priority` |

## Standalone CLI

None — the standalone `main.py` CLI script was removed; use `python run.py` and the API above.

## Docker

    docker build -t scheduler .
    docker run -e SECRET_KEY=... -e DATABASE_URL=... \
      -e GOOGLE_CLIENT_ID=... -e GOOGLE_CLIENT_SECRET=... -p 5000:5000 scheduler

The image runs `flask db upgrade` at startup, then starts gunicorn on port 5000.

CI publishes `ghcr.io/shawila/scheduler` on push to master and deploys via
`/opt/infra` compose. Repo secrets required: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`.

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Project Structure

```
scheduler/
├── app/
│   ├── __init__.py        # Flask app factory
│   ├── config.py          # Configuration from environment
│   ├── extensions.py      # SQLAlchemy / Flask-Mail instances
│   ├── auth.py             # require_auth decorator (Bearer api_token)
│   ├── google_calendar.py  # OAuth flow + credential resolution (direct or pps_auth broker)
│   ├── pps_auth.py         # pps_auth HTTP client for broker-backed Google tokens
│   ├── slots.py            # Pure free-slot computation (testable, no Google deps)
│   ├── main/
│   │   └── routes.py       # /token/revoke
│   ├── booking/
│   │   ├── routes.py       # /book, /confirm-booking
│   │   ├── validation.py   # slot alignment, duration, MX record checks
│   │   ├── events.py       # Google Calendar event creation
│   │   └── email.py        # booking confirmation email
│   └── org/
│       ├── routes.py       # org CRUD, availability, invite/join, register-external
│       ├── selection.py     # picks an available member for a booking
│       └── email.py        # invite email
├── app/models/              # User, Organization, OrganizationMember, OrganizationInvite,
│                            # Booking, PendingBooking
├── migrations/               # Alembic migrations
├── tests/
├── run.py                    # Flask app entry point
├── requirements.txt
└── .env.example
```
