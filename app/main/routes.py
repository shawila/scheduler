import secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from googleapiclient.discovery import build
from app.google_calendar import credentials_from_user, build_oauth_flow
from app.models.user import User
from app.models.exchange_code import ExchangeCode
from app.auth import require_auth
from app.extensions import db
import os

main_bp = Blueprint('main', __name__)

if os.getenv('FLASK_ENV') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


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

    credentials = credentials_from_user(user)
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
