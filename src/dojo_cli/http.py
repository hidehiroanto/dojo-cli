"""
Handles HTTP requests and responses.
"""

from itsdangerous import URLSafeTimedSerializer
import json
import os
from pathlib import Path
import re
from requests import Session

from .config import load_user_config
from .log import error

def delete_cookie():
    cookie_path = Path(load_user_config()['cookie_path']).expanduser().resolve()
    if not cookie_path.is_file():
        error('You are not logged in.')
    cookie_path.unlink()

def load_cookie(cookie_path: Path) -> dict | None:
    assert cookie_path.is_file()
    try:
        cookie_jar = json.loads(cookie_path.read_text())
    except json.JSONDecodeError:
        error('Could not decode cookie JSON')
    if isinstance(cookie_jar, dict):
        session_cookie = cookie_jar.get('session')
        if isinstance(session_cookie, str) and len(session_cookie) > 0:
            return cookie_jar
        else:
            error('Cookie JSON does not have a valid session cookie.')
    else:
        error('Cookie JSON is not a dictionary.')

def save_cookie(cookie_jar: dict):
    cookie_path = Path(load_user_config()['cookie_path']).expanduser().resolve()
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(json.dumps(cookie_jar))

def deserialize_auth_token(auth_token: str) -> list | None:
    token_prefix = 'sk-workspace-local-'
    if auth_token.startswith(token_prefix):
        token_data = URLSafeTimedSerializer('').loads_unsafe(auth_token[len(token_prefix):])[1]
        if isinstance(token_data, list) and len(token_data) == 3:
            if isinstance(token_data[0], int) and isinstance(token_data[1], str) and token_data[2] == 'cli-auth-token':
                return token_data
    return None

def request(url: str, api: bool = True, auth: bool = True, csrf: bool = False, **kwargs):
    user_config = load_user_config()
    session = kwargs.pop('session', Session())
    method = 'POST' if 'data' in kwargs or 'json' in kwargs else 'GET'
    base_url = user_config['base_url']
    headers = kwargs.pop('headers', {})

    if not (url.startswith('http://') or url.startswith('https://')):
        url = base_url + (user_config['api'] if api else '') + url

    if auth:
        dojo_auth_token = os.getenv('DOJO_AUTH_TOKEN', '')
        cookie_path = Path(user_config['cookie_path']).expanduser().resolve()
        if deserialize_auth_token(dojo_auth_token):
            headers['Authorization'] = f'Bearer {dojo_auth_token}'
        elif cookie_path.is_file():
            cookie_jar = load_cookie(cookie_path)
            if cookie_jar:
                headers['Cookie'] = f'session={cookie_jar['session']}'
                if session.get(base_url + '/settings', headers=headers, allow_redirects=False).is_redirect:
                    error('Session expired, please login again.')
            else:
                error('Something went wrong loading the cookie jar.')
        else:
            error('Request is not authorized, please login or run this in the dojo.')

    if csrf:
        nonce = re.search(r''''csrfNonce': "(\w+)"''', session.get(base_url, headers=headers).text)
        if nonce:
            headers['CSRF-Token'] = nonce.group(1)
            if 'data' in kwargs:
                kwargs['data']['nonce'] = nonce.group(1)
        else:
            error('Failed to extract nonce.')

    try:
        return session.request(method, url, headers=headers, **kwargs)
    except Exception as e:
        error(f'Request failed: {e}')
