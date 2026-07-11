from app.extensions import db
from app.models.user import User


class TestPpsUser:
    def test_shell_user_without_google_tokens_is_valid(self, app):
        with app.app_context():
            user = User(email='shell@example.com', pps_user_id='uuid-123', api_token='tok')
            db.session.add(user)
            db.session.commit()
            found = User.query.filter_by(pps_user_id='uuid-123').first()
            assert found is not None
            assert found.token is None

    def test_pps_user_id_is_unique(self, app):
        import pytest
        from sqlalchemy.exc import IntegrityError
        with app.app_context():
            db.session.add(User(email='a@example.com', pps_user_id='dup', api_token='t1'))
            db.session.commit()
            db.session.add(User(email='b@example.com', pps_user_id='dup', api_token='t2'))
            with pytest.raises(IntegrityError):
                db.session.commit()
