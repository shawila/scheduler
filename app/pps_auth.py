import os

import requests


class PpsAuthError(Exception):
    """pps_auth exchange failed for a non-grant reason (network, 5xx)."""


class GrantRevoked(PpsAuthError):
    """The user's Google grant is missing or was revoked."""


def fetch_google_access_token(pps_user_id):
    base_url = os.getenv('PPS_AUTH_BASE_URL', 'http://localhost:4000')
    client_id = os.getenv('SCHEDULER_PPS_CLIENT_ID', 'scheduler')
    client_secret = os.environ['SCHEDULER_PPS_CLIENT_SECRET']

    try:
        resp = requests.post(
            f'{base_url}/google/token',
            json={'user_id': pps_user_id},
            auth=(client_id, client_secret),
            timeout=10,
        )
    except requests.RequestException as exc:
        raise PpsAuthError(f'pps_auth unreachable: {exc}') from exc

    if resp.status_code == 403:
        raise GrantRevoked('Google grant revoked or missing')
    if resp.status_code != 200:
        raise PpsAuthError(f'pps_auth exchange failed with status {resp.status_code}')
    return resp.json()['access_token']
