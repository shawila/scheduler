import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlencode
from flask import Blueprint, request, jsonify, g, session, redirect, current_app
from googleapiclient.discovery import build
from app.google_calendar import google_credentials_for, build_oauth_flow
from app.models.user import User
from app.models.exchange_code import ExchangeCode
from app.auth import require_auth
from app.extensions import db
import os

main_bp = Blueprint('main', __name__)

if os.getenv('FLASK_ENV') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


@main_bp.route('/connect')
def connect():
    redirect_uri = request.args.get('redirect_uri', '')
    state = request.args.get('state', '')
    if not redirect_uri or not state:
        return jsonify({'error': 'redirect_uri and state are required'}), 400

    allowed_hosts = [h.strip() for h in current_app.config['ALLOWED_REDIRECT_HOSTS'].split(',')]
    if urlparse(redirect_uri).netloc not in allowed_hosts:
        return jsonify({'error': 'redirect_uri host not allowed'}), 400

    session['connect_redirect_uri'] = redirect_uri
    session['connect_state'] = state

    flow = build_oauth_flow()
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    return redirect(auth_url)


@main_bp.route('/callback')
def callback():
    flow = build_oauth_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    oauth2_client = build('oauth2', 'v2', credentials=credentials)
    user_info = oauth2_client.userinfo().get().execute()
    user_email = user_info['email']

    user = User.query.filter_by(email=user_email).first()
    token_data = dict(
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        scopes=','.join(credentials.scopes),
    )

    if not user:
        user = User(email=user_email, **token_data)
        db.session.add(user)
    else:
        for key, value in token_data.items():
            setattr(user, key, value)

    user.api_token = secrets.token_urlsafe(32)
    db.session.commit()

    connect_redirect_uri = session.pop('connect_redirect_uri', None)
    connect_state = session.pop('connect_state', None)
    if connect_redirect_uri:
        code = secrets.token_urlsafe(32)
        db.session.add(ExchangeCode(
            code=code,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        ))
        db.session.commit()
        query = urlencode({'code': code, 'state': connect_state})
        return redirect(f'{connect_redirect_uri}?{query}')

    return jsonify({'token': user.api_token})


@main_bp.route('/get-busy-hours', methods=['GET'])
def get_busy_hours():
    user_email = request.args.get('email')
    date_str = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))

    if not user_email:
        return jsonify({'error': 'email parameter is required'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    user = User.query.filter_by(email=user_email).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    credentials = google_credentials_for(user)
    service = build('calendar', 'v3', credentials=credentials)

    time_min = date.strftime('%Y-%m-%dT00:00:00Z')
    time_max = date.strftime('%Y-%m-%dT23:59:59Z')

    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_min,
        timeMax=time_max,
        maxResults=50,
        singleEvents=True,
        orderBy='startTime',
    ).execute()

    events = events_result.get('items', [])
    busy_hours = [
        {'start': e['start']['dateTime'], 'end': e['end']['dateTime']}
        for e in events
        if 'dateTime' in e.get('start', {})
    ]
    return jsonify(busy_hours)


@main_bp.route('/token/exchange', methods=['POST'])
def token_exchange():
    data = request.get_json() or {}
    code = data.get('code', '')
    exchange = ExchangeCode.query.filter_by(code=code).first() if code else None

    if not exchange or exchange.expires_at < datetime.utcnow():
        if exchange:
            db.session.delete(exchange)
            db.session.commit()
        return jsonify({'error': 'Invalid or expired code'}), 401

    user = exchange.user
    db.session.delete(exchange)
    db.session.commit()
    return jsonify({'api_token': user.api_token, 'email': user.email})


@main_bp.route('/token/revoke', methods=['POST'])
@require_auth
def token_revoke():
    g.current_user.api_token = None
    db.session.commit()
    return jsonify({'message': 'Token revoked'})
