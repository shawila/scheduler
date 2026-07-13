---
name: running-scheduler-locally
description: Use when launching, running, smoke-testing, or driving the scheduler Flask app locally — starting the dev server, curling endpoints, verifying a change in the real app, or debugging a 500/KeyError on GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET
---

# Running the Scheduler Locally

Flask app (app factory in `app/__init__.py`, entry point `run.py`). Dev server listens on `http://127.0.0.1:3032`; production runs gunicorn on port 5000 (Dockerfile) — do not change that.

## Launch

```bash
pip install -r requirements.txt      # only if imports fail — deps are plain pip
FLASK_APP=run.py flask db upgrade    # migrate SQLite db
python3 run.py                       # dev server on http://127.0.0.1:3032
```

- Dev port is 3032 by default; override with `PORT=<n> python3 run.py`. Don't use 5000 locally — macOS AirPlay Receiver squats on it and answers 403.
- The database is `instance/app.db` (Flask-SQLAlchemy 3.x resolves `sqlite:///app.db` there). An `app.db` at the repo root is stale — ignore it.
- To stop the server, kill by script name: `pkill -f "run\.py"`. The Werkzeug debug reloader re-execs with a different command line, so matching on `python3 run.py` leaves an orphan serving the port.

## Gotcha: GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are required even for 401s

Most routes use `@require_auth` (`app/auth.py`), and its 401 response builds a Google OAuth URL via `build_oauth_flow()` (`app/google_calendar.py`), which reads `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` from the environment. Without them set, every guarded route 500s with `KeyError: 'GOOGLE_CLIENT_ID'`. For local smoke tests, dummy values are enough:

```bash
export GOOGLE_CLIENT_ID=dummy.apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=dummy
```

Real OAuth flows (the org invite/join flow) and any route that calls the Google Calendar API (org availability, booking creation against a real calendar) need real Google Cloud Console credentials plus a connected user — don't expect those to work with dummy values. For a real OAuth flow in dev, also set `OAUTH_INVITE_REDIRECT_URI=http://localhost:3032/org/join-callback` and `BOOKING_CONFIRM_BASE_URL=http://localhost:3032` — their defaults still point at port 5000.

## Smoke tests

```bash
curl http://127.0.0.1:3032/get-busy-hours
# 400 {"error": "email parameter is required"}  — proves the server is up, no auth needed

curl -X POST http://127.0.0.1:3032/book -H 'Content-Type: application/json' -d '{}'
# 401 {"error": "Unauthorized", "auth_url": "https://accounts.google.com/..."}
```

## Calling authenticated endpoints

Auth is `Authorization: Bearer <User.api_token>`. Seed a local user:

```bash
python3 - <<'EOF'
from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app()
with app.app_context():
    if not User.query.filter_by(email='dev-smoke@example.com').first():
        db.session.add(User(email='dev-smoke@example.com', token='x', refresh_token='x',
                            token_uri='https://oauth2.googleapis.com/token', client_id='dummy',
                            client_secret='dummy', scopes='[]', api_token='dev-local-token'))
        db.session.commit()
EOF

curl -X POST http://127.0.0.1:3032/book \
  -H 'Authorization: Bearer dev-local-token' -H 'Content-Type: application/json' -d '{}'
# 400 {"error": "Missing fields: org_uid, guest_email, guest_name, date, start_time, end_time"}
# — past auth, into real validation
```

## Other entry points

- Tests: `python3 -m pytest tests/ -v` — no Google credentials needed.
- Docker: see README "Docker" section (gunicorn on port 5000, runs migrations at startup).
