from datetime import datetime
from app.extensions import db
from app.models.pending_booking import PendingBooking


class TestPendingBookingTimeZone:
    def test_defaults_to_utc(self, app, authed_user, org_with_owner):
        with app.app_context():
            pending = PendingBooking(
                confirmation_token='tok-1',
                org_id=org_with_owner,
                admin_user_id=authed_user.id,
                guest_email='g@example.com',
                guest_name='Jane',
                start_datetime=datetime(2026, 7, 15, 9, 0),
                end_datetime=datetime(2026, 7, 15, 9, 30),
                expires_at=datetime(2026, 7, 16, 9, 0),
            )
            db.session.add(pending)
            db.session.commit()
            assert pending.time_zone == 'UTC'

    def test_stores_explicit_timezone(self, app, authed_user, org_with_owner):
        with app.app_context():
            pending = PendingBooking(
                confirmation_token='tok-2',
                org_id=org_with_owner,
                admin_user_id=authed_user.id,
                guest_email='g@example.com',
                guest_name='Jane',
                start_datetime=datetime(2026, 7, 15, 0, 0),
                end_datetime=datetime(2026, 7, 15, 0, 30),
                expires_at=datetime(2026, 7, 16, 0, 0),
                time_zone='Asia/Tokyo',
            )
            db.session.add(pending)
            db.session.commit()
            assert pending.time_zone == 'Asia/Tokyo'
