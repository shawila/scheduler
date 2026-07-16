import hmac
import os
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Blueprint, request, jsonify, session, redirect, g
from googleapiclient.discovery import build
from app.extensions import db
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.organization_invite import OrganizationInvite
from app.models.user import User
from app.google_calendar import google_credentials_for, build_oauth_flow, INVITE_REDIRECT_URI
from app.auth import require_auth
from app.org.email import send_invite_email
from app.slots import (compute_available_slots, to_google_utc,
                       DEFAULT_WINDOW_START, DEFAULT_WINDOW_END)

org_bp = Blueprint('org', __name__, url_prefix='/org')

ROLE_RANK = {'employee': 1, 'manager': 2, 'owner': 3}


def _valid_window(window_start, window_end):
    try:
        datetime.strptime(window_start, '%H:%M')
        datetime.strptime(window_end, '%H:%M')
    except ValueError:
        return False
    return window_start < window_end


@org_bp.route('/me', methods=['GET'])
@require_auth
def my_org():
    member = OrganizationMember.query.filter_by(user_id=g.current_user.id).first()
    if not member:
        return jsonify({'error': 'Not a member of any org'}), 404
    org = Organization.query.get(member.org_id)
    return jsonify({
        'org_id': org.id,
        'name': org.name,
        'calendar_id': org.google_calendar_id,
    })


@org_bp.route('/<int:org_uid>/availability', methods=['GET'])
@require_auth
def availability(org_uid):
    tz = request.args.get('tz', 'UTC')
    try:
        zone = ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        return jsonify({'error': f'Unknown timezone: {tz}'}), 400

    try:
        date = datetime.strptime(request.args.get('date', ''), '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    window_start = request.args.get('window_start') or DEFAULT_WINDOW_START
    window_end = request.args.get('window_end') or DEFAULT_WINDOW_END
    if not _valid_window(window_start, window_end):
        return jsonify({'error': 'Invalid booking window'}), 400

    actor = OrganizationMember.query.filter_by(
        user_id=g.current_user.id, org_id=org_uid
    ).first()
    if not actor:
        return jsonify({'error': 'Not a member of this org'}), 403

    members = OrganizationMember.query.filter_by(org_id=org_uid).all()
    local_start = datetime(date.year, date.month, date.day, tzinfo=zone)
    local_end = local_start + timedelta(days=1)
    time_min = to_google_utc(local_start)
    time_max = to_google_utc(local_end)

    members_busy = []
    for member in members:
        credentials = google_credentials_for(member.user)
        service = build('calendar', 'v3', credentials=credentials)
        freebusy = service.freebusy().query(body={
            'timeMin': time_min,
            'timeMax': time_max,
            'timeZone': 'UTC',
            'items': [{'id': 'primary'}],
        }).execute()
        members_busy.append(freebusy['calendars']['primary'].get('busy', []))

    return jsonify({'slots': compute_available_slots(
        members_busy, date, tz, window_start=window_start, window_end=window_end)})


def _create_org_with_calendar(user, org_name, owner_email):
    credentials = google_credentials_for(user)
    service = build('calendar', 'v3', credentials=credentials)

    calendar = service.calendars().insert(body={'summary': org_name}).execute()
    calendar_id = calendar['id']

    # The creator already owns the calendar; Google rejects self-ACL changes
    # with "Cannot change your own access level".
    if (user.email or '').lower() != owner_email.lower():
        service.acl().insert(
            calendarId=calendar_id,
            body={'role': 'owner', 'scope': {'type': 'user', 'value': owner_email}},
        ).execute()

    org = Organization(name=org_name, google_calendar_id=calendar_id)
    db.session.add(org)
    db.session.flush()
    db.session.add(OrganizationMember(org_id=org.id, user_id=user.id, role='owner', priority=1))
    return org


@org_bp.route('/register-external', methods=['POST'])
def register_external():
    expected = os.getenv('HATAN_SERVICE_TOKEN', '')
    provided = request.headers.get('X-Service-Token', '')
    if not expected or not hmac.compare_digest(provided, expected):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    required = ['org_name', 'pps_user_id', 'email']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    user = (User.query.filter_by(pps_user_id=data['pps_user_id']).first()
            or User.query.filter_by(email=data['email']).first())
    if user:
        user.pps_user_id = user.pps_user_id or data['pps_user_id']
    else:
        user = User(email=data['email'], pps_user_id=data['pps_user_id'])
        db.session.add(user)
    user.api_token = secrets.token_urlsafe(32)
    db.session.flush()

    member = OrganizationMember.query.filter_by(user_id=user.id).first()
    if member:
        org = Organization.query.get(member.org_id)
        db.session.commit()
        return jsonify({'org_id': org.id, 'calendar_id': org.google_calendar_id,
                        'api_token': user.api_token}), 200

    org = _create_org_with_calendar(user, data['org_name'], data['email'])
    db.session.commit()
    return jsonify({'org_id': org.id, 'calendar_id': org.google_calendar_id,
                    'api_token': user.api_token}), 201


@org_bp.route('/<int:org_uid>/invite', methods=['POST'])
@require_auth
def invite_member(org_uid):
    data = request.get_json() or {}
    invitee_email = data.get('invitee_email', '').strip()
    role = data.get('role', 'employee')
    priority = int(data.get('priority', 1))

    if not invitee_email:
        return jsonify({'error': 'invitee_email is required'}), 400

    if role not in ROLE_RANK:
        return jsonify({'error': 'role must be owner, manager, or employee'}), 400

    actor_member = OrganizationMember.query.filter_by(
        user_id=g.current_user.id, org_id=org_uid
    ).first()
    if not actor_member:
        return jsonify({'error': 'Not a member of this org'}), 403

    if ROLE_RANK[actor_member.role] < ROLE_RANK['manager']:
        return jsonify({'error': 'Only managers and owners can invite members'}), 403

    if actor_member.role == 'manager' and role != 'employee':
        return jsonify({'error': 'Managers can only invite employees'}), 403

    existing_user = User.query.filter_by(email=invitee_email).first()
    if existing_user and OrganizationMember.query.filter_by(user_id=existing_user.id).first():
        return jsonify({'error': 'User already belongs to an org'}), 400

    existing_invite = OrganizationInvite.query.filter_by(
        org_id=org_uid, invited_email=invitee_email
    ).first()
    if existing_invite:
        if existing_invite.expires_at > datetime.utcnow():
            return jsonify({'error': 'Invite already pending for this email'}), 400
        db.session.delete(existing_invite)

    token = secrets.token_urlsafe(32)
    invite = OrganizationInvite(
        org_id=org_uid,
        invited_email=invitee_email,
        token=token,
        role=role,
        priority=priority,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(invite)
    db.session.commit()

    org = Organization.query.get(org_uid)
    send_invite_email(invitee_email, org.name, org_uid, token)

    return jsonify({'message': f'Invite sent to {invitee_email}'}), 200


@org_bp.route('/<int:org_uid>/join/<token>', methods=['GET'])
def join_org(org_uid, token):
    invite = OrganizationInvite.query.filter_by(token=token).first()
    if not invite:
        return jsonify({'error': 'Invalid invite token'}), 404
    if invite.org_id != org_uid:
        return jsonify({'error': 'Invalid invite token for this org'}), 400
    if invite.expires_at < datetime.utcnow():
        return jsonify({'error': 'Invite link has expired'}), 410

    session['org_invite_token'] = token
    flow = build_oauth_flow(redirect_uri=INVITE_REDIRECT_URI)
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
    )
    session['state'] = state
    return redirect(auth_url)


@org_bp.route('/join-callback', methods=['GET'])
def join_callback():
    invite_token = session.pop('org_invite_token', None)
    if not invite_token:
        return jsonify({'error': 'No invite in progress'}), 400

    invite = OrganizationInvite.query.filter_by(token=invite_token).first()
    if not invite or invite.expires_at < datetime.utcnow():
        return jsonify({'error': 'Invite expired or invalid'}), 410

    flow = build_oauth_flow(redirect_uri=INVITE_REDIRECT_URI)
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    oauth2_client = build('oauth2', 'v2', credentials=credentials)
    user_info = oauth2_client.userinfo().get().execute()
    user_email = user_info['email']

    if user_email != invite.invited_email:
        return jsonify({'error': 'Email mismatch — please log in with the invited email'}), 400

    token_data = dict(
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        scopes=','.join(credentials.scopes),
    )

    user = User.query.filter_by(email=user_email).first()
    if user:
        existing_member = OrganizationMember.query.filter_by(user_id=user.id).first()
        if existing_member:
            if existing_member.org_id != invite.org_id:
                return jsonify({'error': 'Already belong to another org'}), 400
            for key, value in token_data.items():
                setattr(user, key, value)
            user.api_token = secrets.token_urlsafe(32)
            db.session.delete(invite)
            db.session.commit()
            return jsonify({'token': user.api_token})
        for key, value in token_data.items():
            setattr(user, key, value)
    else:
        user = User(email=user_email, **token_data)
        db.session.add(user)

    user.api_token = secrets.token_urlsafe(32)
    db.session.flush()

    org = Organization.query.get(invite.org_id)
    owner_member = OrganizationMember.query.filter_by(org_id=invite.org_id, role='owner').first()
    if owner_member:
        owner_creds = google_credentials_for(owner_member.user)
        cal_service = build('calendar', 'v3', credentials=owner_creds)
        cal_service.acl().insert(
            calendarId=org.google_calendar_id,
            body={'role': 'writer', 'scope': {'type': 'user', 'value': user_email}},
        ).execute()

    member = OrganizationMember(
        org_id=invite.org_id,
        user_id=user.id,
        role=invite.role,
        priority=invite.priority,
    )
    db.session.add(member)
    db.session.delete(invite)
    db.session.commit()

    return jsonify({'token': user.api_token})


@org_bp.route('/<int:org_uid>/users/<int:user_id>', methods=['PUT'])
@require_auth
def update_member(org_uid, user_id):
    data = request.get_json() or {}
    new_role = data.get('role')
    new_priority = data.get('priority')

    actor_member = OrganizationMember.query.filter_by(
        user_id=g.current_user.id, org_id=org_uid
    ).first()
    if not actor_member:
        return jsonify({'error': 'Not a member of this org'}), 403

    target_member = OrganizationMember.query.filter_by(
        user_id=user_id, org_id=org_uid
    ).first()
    if not target_member:
        return jsonify({'error': 'Member not found in this org'}), 404

    actor_rank = ROLE_RANK[actor_member.role]
    target_rank = ROLE_RANK[target_member.role]

    if actor_rank < ROLE_RANK['manager']:
        return jsonify({'error': 'Employees cannot update role or priority'}), 403

    if actor_rank == ROLE_RANK['manager']:
        if target_rank >= ROLE_RANK['manager']:
            return jsonify({'error': 'Managers can only update employees'}), 403
        if new_role is not None and new_role != 'employee':
            return jsonify({'error': 'Managers can only assign employee role'}), 403

    if new_role is not None:
        if new_role not in ROLE_RANK:
            return jsonify({'error': 'Invalid role'}), 400
        target_member.role = new_role

    if new_priority is not None:
        target_member.priority = int(new_priority)

    db.session.commit()
    return jsonify({'message': 'Updated'}), 200
