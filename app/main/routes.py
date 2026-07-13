from flask import Blueprint, g, jsonify
from app.auth import require_auth
from app.extensions import db

main_bp = Blueprint('main', __name__)


@main_bp.route('/token/revoke', methods=['POST'])
@require_auth
def token_revoke():
    g.current_user.api_token = None
    db.session.commit()
    return jsonify({'message': 'Token revoked'})
