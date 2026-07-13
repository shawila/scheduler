from datetime import datetime
from app.extensions import db


class PendingBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    confirmation_token = db.Column(db.String(100), unique=True, nullable=False)
    org_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    guest_email = db.Column(db.String(120), nullable=False)
    guest_name = db.Column(db.String(200), nullable=False)
    time_zone = db.Column(db.String(50), nullable=False, default='UTC')
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    org = db.relationship('Organization')
    admin = db.relationship('User')

    def __repr__(self):
        return f'<PendingBooking {self.guest_email} @ {self.start_datetime}>'
