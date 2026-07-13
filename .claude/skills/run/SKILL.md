---
name: run
description: Use when launching, running, smoke-testing, or driving the scheduler Flask app locally — starting the dev server, curling endpoints, verifying a change in the real app, or debugging a 500/FileNotFoundError on credentials.json
---

# Running the Scheduler Locally

Flask app (app factory in `app/__init__.py`, entry point `run.py`). Dev server listens on `http://127.0.0.1:3032`; production runs gunicorn on port 5000 (Dockerfile) — do not change that.

## Dependency: pps_auth

Scheduler calls `pps_auth` (default `PPS_AUTH_BASE_URL=http://localhost:4000`) for the Google token exchange. Check it's up before launching:

```bash
curl -sf http://localhost:4000/.well-known/openid-configuration > /dev/null && echo up || echo down
```

If it's down, start it using the sister project's own `run` skill — from `/Users/shawila/Workspace/shawila/pps_auth`:

```bash
cd /Users/shawila/Workspace/shawila/pps_auth
cargo run > /tmp/pps_auth.log 2>&1 &
disown
for i in {1..30}; do
  curl -sf http://localhost:4000/.well-known/openid-configuration > /dev/null && break
  sleep 1
done
```

Requires Postgres running at `DATABASE_URL` and a `.env` in `pps_auth` — see that project's `.claude/skills/run/SKILL.md` for prerequisites and migration gotchas. Logs at `/tmp/pps_auth.log`; stop with `pkill -f "target/debug/pps_auth"`.

## Launch

```bash
pip install -r requirements.txt      # only if imports fail — deps are plain pip
FLASK_APP=run.py flask db upgrade    # migrate SQLite db
python3 run.py                       # dev server on http://127.0.0.1:3032
```

- Dev port is 3032 by default; override with `PORT=<n> python3 run.py`. Don't use 5000 locally — macOS AirPlay Receiver squats on it and answers 403.
- No `.env` required — `app/config.py` has working defaults for local dev.
- The database is `instance/app.db` (Flask-SQLAlchemy 3.x resolves `sqlite:///app.db` there). An `app.db` at the repo root is stale — ignore it.
- To stop the server, kill by script name: `pkill -f "run\.py"`. The Werkzeug debug reloader re-execs with a different command line, so matching on `python3 run.py` leaves an orphan serving the port.

## Gotcha: credentials.json is required even for 401s

Most routes use `@require_auth` (`app/auth.py`), and its 401 response builds a Google OAuth URL from `credentials.json` in the project root. Without the file, every guarded route 500s with `FileNotFoundError: credentials.json`. For local smoke tests a dummy is enough (gitignored — never commit):

```bash
cat > credentials.json <<'EOF'
{"web": {"client_id": "dummy.apps.googleusercontent.com", "client_secret": "dummy",
 "auth_uri": "https://accounts.google.com/o/oauth2/auth",
 "token_uri": "https://oauth2.googleapis.com/token",
 "redirect_uris": ["http://localhost:3032/callback"]}}
EOF
```

Real OAuth flows (`/connect`, `/callback`) and any route that calls the Google Calendar API (`/get-busy-hours` with a real email, `/confirm-booking/<token>`, org availability) need a real `credentials.json` from Google Cloud Console plus a connected user — don't expect those to work with the dummy. For a real OAuth flow in dev, also set `OAUTH_REDIRECT_URI=http://localhost:3032/callback` and `BOOKING_CONFIRM_BASE_URL=http://localhost:3032` — their defaults still point at port 5000.

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

- CLI: `python3 main.py` prints today's free slots; uses cached `token.pickle`, needs a real `credentials.json` to re-auth.
- Tests: `python3 -m pytest tests/ -v` — no Google credentials needed.
- Docker: see README "Docker" section (gunicorn on port 5000, runs migrations at startup).
