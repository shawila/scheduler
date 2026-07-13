# Backlog

Features and improvements deferred from completed design sessions. Pick these up when prioritizing future work.

---

## Timezone support follow-ups

- **`confirm_booking` day-boundary timezone test gap**: `TestConfirmBookingTimezone` (added in `2026-07-13-timezone-support.md` Task 6) asserts the reconstructed local time and zone key, but its fixture uses a pending row whose local day matches its UTC day (`02:00 UTC` → `11:00 JST`, same calendar date). It doesn't exercise a pending row whose *local* day differs from its *UTC* day (e.g. stored `2024-08-01T15:00Z` → `2024-08-02 00:00 JST`) — the equivalent case is covered for `book()`/availability but not for the confirm-time reconstruction path. The reconstruction logic (`pending.start_datetime.replace(tzinfo=timezone.utc).astimezone(zone)` in `app/booking/routes.py`) is correct by inspection and shares the same round-trip logic proven elsewhere, so this is a coverage gap, not a known bug — but worth closing for completeness.

## Unused-by-hatan flows (2026-07-13 audit)

Cross-checked against hatan's `Scheduler::Client` (`app/services/scheduler/client.rb`) and its callers. Only `register-external`, `availability`, `book`, and `revoke_token` are exercised by hatan today. Two flows below have no caller in hatan but were kept rather than deleted, since they look like intentional scaffolding rather than accidental leftovers — revisit once hatan's product direction confirms whether they'll be used.

- **Team invite/role-management flow is unused**: `POST /org/<id>/invite`, `GET /org/<id>/join/<token>`, `GET /org/join-callback`, `PUT /org/<id>/users/<id>`, and the `OrganizationInvite` model have no caller in hatan's app code (only in scheduler's own tests). This looks like scaffolding for a planned-but-not-yet-built hatan team-management feature. If hatan never grows that UI, this whole flow (plus direct-OAuth token storage on `User.token`/`refresh_token`/etc., only ever populated by this flow) becomes a second dead-code candidate.
- **Pending-booking / email-confirmation flow is unreachable via hatan (for now)**: hatan's `Calendar::BookingsController#create` always calls `POST /book` with `confirmed: true` (see `app/controllers/calendar/bookings_controller.rb` in hatan), so the `PendingBooking` model, `GET /confirm-booking/<token>`, and `send_confirmation_email` are currently never exercised by hatan. **Update (2026-07-13): hatan is planning to build guest-facing email-confirmation booking next**, i.e. a path that calls `POST /book` with `confirmed: false` (or omitted) and relies on `GET /confirm-booking/<token>` to complete the booking. Not a removal candidate — keep this flow as-is and expect hatan-side integration work to land soon. Worth double-checking the flow end-to-end (confirmation email content/links, `BOOKING_CONFIRM_BASE_URL`, token expiry) before hatan wires it up.

Already removed (2026-07-13): the original direct-OAuth connect flow (`GET /connect`, `GET /callback`, `POST /token/exchange`, `POST /org/register`, `ExchangeCode` model) — confirmed fully superseded by the `pps_auth` broker flow (`register-external`) per hatan's own `2026-07-11-ppsauth-google-token-broker-design.md`, and unused by any hatan code path.
