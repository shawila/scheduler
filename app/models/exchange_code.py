from app.extensions import db


class ExchangeCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship('User')

    def __repr__(self):
        return f'<ExchangeCode user_id={self.user_id}>'
