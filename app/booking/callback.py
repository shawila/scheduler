import os
import logging
import requests

logger = logging.getLogger(__name__)


def notify_callback(callback_url, payload):
    if not callback_url:
        return
    token = os.getenv('HATAN_SERVICE_TOKEN', '')
    try:
        requests.post(callback_url, json=payload, headers={'X-Service-Token': token}, timeout=5)
    except requests.RequestException as exc:
        logger.warning('booking callback POST failed: %s', exc)
    except Exception as exc:  # noqa: BLE001 — must never break the guest-facing confirmation
        logger.warning('booking callback POST failed: %s', exc)
