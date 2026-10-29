"""Microsoft delegated sign-in for the local evaluator's sending account."""
import os
from pathlib import Path
import tempfile
import threading
import uuid

from config import BACKEND_DIR

SCOPES = ['https://graph.microsoft.com/Mail.Send']
CACHE_PATH = BACKEND_DIR / '.outlook_token_cache.json'
AUTH_LOCK = threading.Lock()


class OutlookSignInRequired(Exception):
    pass


def _application(config):
    # Keep this optional so existing SMTP installations still start without MSAL.
    try:
        import msal
    except ImportError:
        raise OutlookSignInRequired('Install backend/requirements.txt before connecting Outlook.') from None
    try:
        tenant = str(uuid.UUID(config['tenant_id']))
        client = str(uuid.UUID(config['client_id']))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise OutlookSignInRequired('Run backend/connect_outlook.py with the university tenant ID and app client ID.') from None
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text(encoding='utf-8'))
    app = msal.PublicClientApplication(client, authority=f'https://login.microsoftonline.com/{tenant}',
                                       token_cache=cache, timeout=20)
    return app, cache


def _save_cache(cache):
    if not cache.has_state_changed:
        return
    # Atomic replacement prevents an interrupted refresh corrupting the cache.
    fd, filename = tempfile.mkstemp(dir=CACHE_PATH.parent, prefix='.outlook-cache-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(cache.serialize())
        os.replace(filename, CACHE_PATH)
    finally:
        if Path(filename).exists():
            Path(filename).unlink()


def connect_sender(config):
    """Explicit administrator-run setup only; never invoked while grading."""
    with AUTH_LOCK:
        app, cache = _application(config)
        result = app.acquire_token_interactive(scopes=SCOPES, login_hint=config['sender'], timeout=300)
        if 'access_token' not in result:
            raise OutlookSignInRequired('Microsoft sign-in was not completed. Check university app consent and sign-in policy with IT.')
        username = result.get('id_token_claims', {}).get('preferred_username', '')
        if username.casefold() != config['sender'].casefold():
            raise OutlookSignInRequired('Sign in using the configured university sending address, then retry.')
        _save_cache(cache)


def sender_access_token(config):
    """Refresh silently; never open a browser from the evaluation worker."""
    with AUTH_LOCK:
        app, cache = _application(config)
        accounts = app.get_accounts(username=config['sender'])
        result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        _save_cache(cache)
        if not result or 'access_token' not in result:
            raise OutlookSignInRequired('University sender needs sign-in. Run backend/connect_outlook.py again; completed reports remain available.')
        return result['access_token']
