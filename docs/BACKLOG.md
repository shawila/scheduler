# Backlog

Features and improvements deferred from completed design sessions. Pick these up when prioritizing future work.

---

## Timezone support follow-ups

- **`confirm_booking` day-boundary timezone test gap**: `TestConfirmBookingTimezone` (added in `2026-07-13-timezone-support.md` Task 6) asserts the reconstructed local time and zone key, but its fixture uses a pending row whose local day matches its UTC day (`02:00 UTC` → `11:00 JST`, same calendar date). It doesn't exercise a pending row whose *local* day differs from its *UTC* day (e.g. stored `2024-08-01T15:00Z` → `2024-08-02 00:00 JST`) — the equivalent case is covered for `book()`/availability but not for the confirm-time reconstruction path. The reconstruction logic (`pending.start_datetime.replace(tzinfo=timezone.utc).astimezone(zone)` in `app/booking/routes.py`) is correct by inspection and shares the same round-trip logic proven elsewhere, so this is a coverage gap, not a known bug — but worth closing for completeness.
- **`compute_free_slots` is dead code**: `app/slots.py`'s `compute_free_slots` (the original single-member, naive-UTC slot helper) lost its last caller once `compute_available_slots` became the only slot-computation path used by the availability endpoint. It's still exercised directly by `tests/test_scheduler.py`, but nothing in `app/` calls it anymore. Candidate for deletion (along with its dedicated tests) once confirmed there's no external/undocumented caller.
