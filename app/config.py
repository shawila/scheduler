import os

DB_SCHEMA = 'scheduler'
_DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///app.db')
_ENGINE_OPTIONS = (
    {'connect_args': {'options': f'-csearch_path={DB_SCHEMA}'}}
    if _DATABASE_URL.startswith('postgresql')
    else {}
)


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')
    SQLALCHEMY_DATABASE_URI = _DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _ENGINE_OPTIONS

    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_USERNAME')

    BOOKING_CONFIRM_BASE_URL = os.getenv('BOOKING_CONFIRM_BASE_URL', 'http://localhost:5000')
