import secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.models.pending_booking import PendingBooking
from app.models.booking import Booking
from app.booking.validation import is_slot_aligned, validate_booking_duration, check_mx_record
from app.booking.email import send_confirmation_email
from app.booking.events import create_calendar_event
from app.org.selection import select_admin
from app.auth import require_auth

booking_bp = Blueprint('booking', __name__)


@booking_bp.route('/book', methods=['POST'])
@require_auth
def book():
    data = request.get_json() or {}

    required = ['org_uid', 'guest_email', 'guest_name', 'date', 'start_time', 'end_time']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    try:
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        start_time = datetime.strptime(data['start_time'], '%H:%M')
        end_time = datetime.strptime(data['end_time'], '%H:%M')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    start_dt = datetime(date.year, date.month, date.day, start_time.hour, start_time.minute)
    end_dt = datetime(date.year, date.month, date.day, end_time.hour, end_time.minute)

    if not is_slot_aligned(start_dt) or not is_slot_aligned(end_dt):
        return jsonify({'error': 'Times must be aligned to 30-minute slots (minutes must be 00 or 30)'}), 400

    valid, error = validate_booking_duration(start_dt, end_dt)
    if not valid:
        return jsonify({'error': error}), 400

    org = Organization.query.get(data['org_uid'])
    if not org:
        return jsonify({'error': 'Organization not found'}), 400

    if not check_mx_record(data['guest_email']):
        return jsonify({'error': 'Could not verify guest email domain'}), 400

    members = OrganizationMember.query.filter_by(org_id=org.id).all()
    preferred_id = int(data['user_id']) if data.get('user_id') else None
    chosen_admin = select_admin(members, start_dt, end_dt, preferred_user_id=preferred_id)

    if not chosen_admin:
        return jsonify({'error': 'No admin available for the requested time slot'}), 409

    if data.get('confirmed') is True:
        created_event = create_calendar_event(
            chosen_admin, org, data['guest_email'], data['guest_name'], start_dt, end_dt,
        )
        if not created_event:
            return jsonify({'error': 'Time slot is no longer available'}), 409

        booking = Booking(
            google_event_id=created_event['id'],
            org_id=org.id,
            admin_user_id=chosen_admin.id,
            guest_email=data['guest_email'],
            guest_name=data['guest_name'],
            start_datetime=start_dt,
            end_datetime=end_dt,
        )
        db.session.add(booking)
        db.session.commit()

        return jsonify({
            'event_id': created_event['id'],
            'title': created_event['summary'],
            'start': created_event['start']['dateTime'],
            'end': created_event['end']['dateTime'],
            'html_link': created_event.get('htmlLink'),
        }), 201

    token = secrets.token_urlsafe(32)
    pending = PendingBooking(
        confirmation_token=token,
        org_id=org.id,
        admin_user_id=chosen_admin.id,
        guest_email=data['guest_email'],
        guest_name=data['guest_name'],
        start_datetime=start_dt,
        end_datetime=end_dt,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(pending)
    db.session.commit()

    send_confirmation_email(data['guest_email'], data['guest_name'], token)

    return jsonify({'message': f'Confirmation email sent to {data["guest_email"]}'}), 201


@booking_bp.route('/confirm-booking/<token>', methods=['GET'])
def confirm_booking(token):
    pending = PendingBooking.query.filter_by(confirmation_token=token).first()
    if not pending:
        return jsonify({'error': 'Invalid confirmation token'}), 404

    if pending.expires_at < datetime.utcnow():
        return jsonify({'error': 'Confirmation link has expired'}), 410

    admin = User.query.get(pending.admin_user_id)
    if not admin:
        return jsonify({'error': 'Admin account not found'}), 400

    org = Organization.query.get(pending.org_id)

    created_event = create_calendar_event(
        admin, org, pending.guest_email, pending.guest_name,
        pending.start_datetime, pending.end_datetime,
    )
    if not created_event:
        return jsonify({'error': 'Time slot is no longer available'}), 409

    booking = Booking(
        google_event_id=created_event['id'],
        org_id=pending.org_id,
        admin_user_id=pending.admin_user_id,
        guest_email=pending.guest_email,
        guest_name=pending.guest_name,
        start_datetime=pending.start_datetime,
        end_datetime=pending.end_datetime,
    )
    db.session.add(booking)
    db.session.delete(pending)
    db.session.commit()

    return jsonify({
        'event_id': created_event['id'],
        'title': created_event['summary'],
        'start': created_event['start']['dateTime'],
        'end': created_event['end']['dateTime'],
        'html_link': created_event.get('htmlLink'),
    }), 200
