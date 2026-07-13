# Google Calendar Authorization

How scheduler gets access to a Google Calendar on behalf of an org, and the two
distinct paths that lead there: **broker-backed** (via hatan + pps_auth) and
**direct-OAuth** (scheduler's own invite/join flow).

---

## Overview

| Concern | Owned by |
|---|---|
| Google OAuth app credentials (client id/secret) | scheduler itself (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` env vars) |
| Google consent screen + refresh-token storage for hatan-connected orgs | pps_auth (encrypted `provider_tokens` table) |
| Short-lived access tokens for broker-backed users | pps_auth's `/google/token` broker endpoint |
| Org/user/booking domain data | scheduler's own DB (`app/models/`) |

Two call sites in scheduler still build a Google OAuth `Flow` directly
(`app/google_calendar.py:build_oauth_flow`): `generate_auth_url()`
(`app/auth.py`, used in `require_auth`'s 401 response) and the org invite/join
flow (`app/org/routes.py:203,222`). Neither is reached by hatan — see
[Direct-OAuth flow](#direct-oauth-flow-legacy-invitejoin) below.

---

## Broker-backed flow (hatan admin connects a calendar)

This is the only path hatan actually exercises today.

```
1. Admin → hatan admin/widget_configurations/edit
   Clicks "Connect Google Calendar"

2. Browser → POST /users/auth/pps_auth_calendar
   OmniAuth redirects to pps_auth's /authorize
   requesting scopes [openid, email, profile, calendar]

3. pps_auth /auth/google/start
   Sees "calendar" scope → adds access_type=offline&prompt=consent
   → redirects to Google's real consent screen

4. Admin grants calendar access on Google's consent screen

5. Google → pps_auth /auth/google/callback
   pps_auth exchanges the code with Google using ITS OWN
   GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET, encrypts the refresh_token
   (TOKEN_ENCRYPTION_KEY, AES-256-GCM), stores it in provider_tokens
   keyed by (user_id, "google")

6. pps_auth → hatan /users/auth/pps_auth_calendar/callback
   hatan gets the authenticated identity (uid = pps_user_id, email)

7. hatan → POST scheduler /org/register-external
   Body: {org_name, pps_user_id, email}
   Header: X-Service-Token: HATAN_SERVICE_TOKEN

8. scheduler creates/finds the User (pps_user_id set → "broker-backed"),
   creates the Organization + a real Google Calendar via its own service
   account, returns {org_id, calendar_id, api_token}

9. hatan stores a SchedulerConnection (api_token, scheduler_org_uid,
   google_email) and builds a calendar embed URL from calendar_id
```

**At no point in this flow does scheduler build its own Google OAuth `Flow`
or touch `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`.**

### Fetching an access token for a broker-backed user

Whenever scheduler needs to call the Google Calendar API for a broker-backed
user (availability checks, ACL grants, event creation), it asks pps_auth for
a short-lived token instead of doing OAuth itself:

```
scheduler → POST pps_auth /google/token
  Basic auth: SCHEDULER_PPS_CLIENT_ID / SCHEDULER_PPS_CLIENT_SECRET
  Body: {user_id: pps_user_id}
(app/pps_auth.py:fetch_google_access_token → pps_auth/src/broker.rs)

pps_auth decrypts the stored refresh_token, exchanges it with Google
(grant_type=refresh_token, using pps_auth's own Google app credentials),
returns a short-lived access_token to scheduler.
```

`google_credentials_for(user)` (`app/google_calendar.py`) is the single
dispatch point: broker-backed users (`pps_user_id` set) go through
`fetch_google_access_token`; legacy direct-OAuth users use their stored
`token`/`refresh_token` columns instead.

---

## Direct-OAuth flow (legacy invite/join)

`build_oauth_flow()` is still used by two routes that let a user connect
Google Calendar directly to scheduler, bypassing hatan/pps_auth entirely:

- `GET /org/<org_uid>/join/<token>` — invitee clicks an invite link, redirected
  to Google's consent screen
- `GET /org/join-callback` — OAuth redirect target, exchanges the code and
  stores `token`/`refresh_token`/etc. directly on the `User` row
- `require_auth`'s 401 response (`generate_auth_url()`) also builds an
  auth URL via the same flow, for any unauthenticated request

As of 2026-07-13, this flow's OAuth client credentials come from
`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` env vars (previously a
`credentials.json` file downloaded from Google Cloud Console — replaced to
match pps_auth's own env-var-based approach, since the file added an extra
secret-management burden with no security benefit over env vars).

**This flow has no caller in hatan** (confirmed by tracing hatan's
`Scheduler::Client` and its callers) — see `docs/BACKLOG.md`'s "Direct-OAuth
surface is a deprecation candidate" entry for the full list of code this
takes with it if/when it's confirmed dead.

---

## Environment Variables

| Variable | Used by | Description |
|---|---|---|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Direct-OAuth flow only | scheduler's own Google Cloud OAuth Client (Web type) |
| `PPS_AUTH_BASE_URL` | Broker-backed flow | pps_auth base URL for the `/google/token` exchange |
| `SCHEDULER_PPS_CLIENT_ID` / `SCHEDULER_PPS_CLIENT_SECRET` | Broker-backed flow | scheduler's own service-client credentials against pps_auth (seeded via `cargo run --bin seed` in pps_auth), unrelated to Google's OAuth credentials |
| `HATAN_SERVICE_TOKEN` | `POST /org/register-external` | Shared secret with hatan for service-authenticated org registration |

---

## See Also

- hatan's [`docs/wiki/auth.md`](../../../hatan/docs/wiki/auth.md) — hatan's own login/session auth against pps_auth (a separate concern from calendar authorization)
- `docs/BACKLOG.md` — deprecation tracking for the direct-OAuth surface
