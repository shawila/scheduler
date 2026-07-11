import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from app.models.user import User
from app.pps_auth import fetch_google_access_token

CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
REDIRECT_URI = os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:5000/callback')
INVITE_REDIRECT_URI = os.getenv('OAUTH_INVITE_REDIRECT_URI', 'http://localhost:5000/org/join-callback')


def build_oauth_flow(redirect_uri=None):
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri or REDIRECT_URI,
    )


def credentials_from_user(user: User) -> Credentials:
    return Credentials(
        token=user.token,
        refresh_token=user.refresh_token,
        token_uri=user.token_uri,
        client_id=user.client_id,
        client_secret=user.client_secret,
        scopes=user.scopes.split(','),
    )


def google_credentials_for(user) -> Credentials:
    """Broker-backed users (pps_user_id set) get a short-lived token from
    pps_auth; legacy users keep their stored refresh-token credentials."""
    if user.pps_user_id:
        return Credentials(token=fetch_google_access_token(user.pps_user_id))
    return credentials_from_user(user)
