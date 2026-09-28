# Backlog

Features and improvements deferred from completed design sessions. Pick these up when prioritizing future work.

---

## Timezone support follow-ups

- **`confirm_booking` day-boundary timezone test gap**: `TestConfirmBookingTimezone` (added in `2026-07-13-timezone-support.md` Task 6) asserts the reconstructed local time and zone key, but its fixture uses a pending row whose local day matches its UTC day (`02:00 UTC` → `11:00 JST`, same calendar date). It doesn't exercise a pending row whose *local* day differs from its *UTC* day (e.g. stored `2024-08-01T15:00Z` → `2024-08-02 00:00 JST`) — the equivalent case is covered for `book()`/availability but not for the confirm-time reconstruction path. The reconstruction logic (`pending.start_datetime.replace(tzinfo=timezone.utc).astimezone(zone)` in `app/booking/routes.py`) is correct by inspection and shares the same round-trip logic proven elsewhere, so this is a coverage gap, not a known bug — but worth closing for completeness.

## Unused-by-hatan flows (2026-07-13 audit)

Cross-checked against hatan's `Scheduler::Client` (`app/services/scheduler/client.rb`) and its callers. Only `register-external`, `availability`, `book`, and `revoke_token` are exercised by hatan today. Two flows below have no caller in hatan but were kept rather than deleted, since they look like intentional scaffolding rather than accidental leftovers — revisit once hatan's product direction confirms whether they'll be used.

- **Team invite/role-management flow is unused**: `POST /org/<id>/invite`, `GET /org/<id>/join/<token>`, `GET /org/join-callback`, `PUT /org/<id>/users/<id>`, and the `OrganizationInvite` model have no caller in hatan's app code (only in scheduler's own tests). This looks like scaffolding for a planned-but-not-yet-built hatan team-management feature. If hatan never grows that UI, this whole flow (plus direct-OAuth token storage on `User.token`/`refresh_token`/etc., only ever populated by this flow) becomes a second dead-code candidate.
- **Pending-booking / email-confirmation flow is now used by hatan**: hatan's chat-widget booking (`Api::Widget::BookingsController#create`) calls `POST /book` with `confirmed: false` and a `callback_url`, storing a `PendingBooking`; `GET /confirm-booking/<token>` later creates the `Booking` and notifies hatan's `Api::Scheduler::BookingsController#callback`. **Update (2026-09-28): confirmed wired up and live** — no longer a removal or "unused" candidate. (hatan's dashboard booking, `Calendar::BookingsController#create`, still always calls `confirmed: true` and skips this flow — that path is unaffected.)

Already removed (2026-07-13): the original direct-OAuth connect flow (`GET /connect`, `GET /callback`, `POST /token/exchange`, `POST /org/register`, `ExchangeCode` model) — confirmed fully superseded by the `pps_auth` broker flow (`register-external`) per hatan's own `2026-07-11-ppsauth-google-token-broker-design.md`, and unused by any hatan code path.

## Direct-OAuth surface is a deprecation candidate (2026-07-13)

`credentials.json` was replaced with `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` env vars in `build_oauth_flow()` (`app/google_calendar.py`) this session — a mechanical swap, not a scope change. But tracing the full hatan admin-connects-a-calendar flow during that work confirmed the same conclusion as the audit above from the *other* direction: hatan's calendar-connect UI goes entirely through OmniAuth → pps_auth → `POST /org/register-external`, and never touches scheduler's own OAuth endpoints. Combined with the "Team invite/role-management flow is unused" finding above, this means the following are all one dead-code cluster once hatan's team-management UI is confirmed as never landing:

- `build_oauth_flow()` / `generate_auth_url()` (`app/auth.py`) — the direct-OAuth URL built into every `require_auth` 401 response
- `GET /org/<id>/join/<token>`, `GET /org/join-callback` (`app/org/routes.py`) — the invite-accept OAuth handshake
- `User.token`/`refresh_token`/`token_uri`/`client_id`/`client_secret` columns — only ever populated by the above
- The `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` env vars themselves and their Google Cloud OAuth Client registration

Not removing now since the invite/join flow is still kept intentionally per the audit above — but if that flow is ever confirmed dead, this whole direct-OAuth surface should go with it in the same pass.
