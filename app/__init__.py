from flask import Flask
from flask_migrate import Migrate
from app.config import Config
from app.extensions import db, mail
from app.main.routes import main_bp


def create_app(config_override=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    db.init_app(app)
    mail.init_app(app)
    Migrate(app, db)

    app.register_blueprint(main_bp)

    from app.booking.routes import booking_bp
    app.register_blueprint(booking_bp)

    from app.org.routes import org_bp
    app.register_blueprint(org_bp)

    from flask import jsonify
    from app.pps_auth import GrantRevoked, PpsAuthError

    @app.errorhandler(GrantRevoked)
    def handle_grant_revoked(exc):
        return jsonify({'error': 'google grant revoked'}), 401

    @app.errorhandler(PpsAuthError)
    def handle_pps_auth_error(exc):
        return jsonify({'error': 'calendar token service unavailable'}), 503

    with app.app_context():
        from app.models.pending_booking import PendingBooking  # noqa: F401
        from app.models.booking import Booking  # noqa: F401
        from app.models.organization import Organization  # noqa: F401
        from app.models.organization_member import OrganizationMember  # noqa: F401
        from app.models.organization_invite import OrganizationInvite  # noqa: F401
        if app.config.get('TESTING'):
            db.create_all()

    return app
