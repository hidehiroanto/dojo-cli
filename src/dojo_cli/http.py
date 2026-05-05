"""Handles HTTP requests and responses."""

import json
import os
from pathlib import Path
import re
from typing import Optional, cast

from itsdangerous import URLSafeTimedSerializer
from niquests import Session

from .config import load_user_config
from .log import error

session_cache: Optional[Session] = None
cookie_cache: Optional[dict] = None
cookie_cache_path: Optional[Path] = None
cookie_cache_mtime: Optional[int] = None

def get_session() -> Session:
    global session_cache
    if session_cache is None:
        session_cache = Session()
    return session_cache

def clear_cookie_cache():
    global cookie_cache, cookie_cache_path, cookie_cache_mtime
    cookie_cache = None
    cookie_cache_path = None
    cookie_cache_mtime = None

def delete_cookie():
    cookie_path = Path(load_user_config()['cookie_path']).expanduser().resolve()
    if not cookie_path.is_file():
        error('You are not logged in.')
    cookie_path.unlink()
    clear_cookie_cache()

def load_cookie(cookie_path: Path) -> Optional[dict]:
    if not cookie_path.is_file():
        error('You are not logged in.')
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

def get_cached_cookie(cookie_path: Path) -> dict:
    global cookie_cache, cookie_cache_path, cookie_cache_mtime
    cookie_mtime = cookie_path.stat().st_mtime_ns
    if cookie_cache is None or cookie_cache_path != cookie_path or cookie_cache_mtime != cookie_mtime:
        cookie_cache = load_cookie(cookie_path)
        cookie_cache_path = cookie_path
        cookie_cache_mtime = cookie_mtime
    cached_cookie = cookie_cache
    if cached_cookie is None:
        error('Something went wrong loading the cookie jar.')
        raise RuntimeError('unreachable')
    return cached_cookie

def save_cookie(cookie_jar: dict):
    cookie_path = Path(load_user_config()['cookie_path']).expanduser().resolve()
    cookie_path.parent.mkdir(0o755, True, True)
    cookie_path.write_text(json.dumps(cookie_jar))
    clear_cookie_cache()

def deserialize_auth_token(auth_token: str) -> Optional[list[int | str]]:
    token_prefix = 'sk-workspace-local-'
    if auth_token.startswith(token_prefix):
        token_data = URLSafeTimedSerializer('').loads_unsafe(auth_token[len(token_prefix):])[1]
        if isinstance(token_data, list) and len(token_data) == 3:
            if isinstance(token_data[0], int) and isinstance(token_data[1], str) and token_data[2] == 'cli-auth-token':
                return token_data
    return None

def request(url: str, api: bool = True, auth: bool = True, csrf: bool = False, **kwargs):
    user_config = load_user_config()
    session = kwargs.pop('session', None)
    if session is None:
        session = get_session()
    method = kwargs.pop('method', 'POST' if 'data' in kwargs or 'json' in kwargs else 'GET')
    base_url = user_config['base_url']
    headers = dict(kwargs.pop('headers', {}))

    if not (url.startswith('http://') or url.startswith('https://')):
        url = base_url + (user_config['api'] if api else '') + url

    if auth:
        dojo_auth_token = os.getenv('DOJO_AUTH_TOKEN', '')
        cookie_path = Path(user_config['cookie_path']).expanduser().resolve()
        if deserialize_auth_token(dojo_auth_token):
            headers['Authorization'] = f'Bearer {dojo_auth_token}'
        elif cookie_path.is_file():
            cookie_jar = get_cached_cookie(cookie_path)
            headers['Cookie'] = f'session={cookie_jar['session']}'
        else:
            error('Request is not authorized, please login or run this in the dojo.')

    if csrf:
        csrf_response = session.get(base_url, headers=headers, allow_redirects=False)
        if csrf_response.is_redirect:
            error('Session expired, please login again.')
        nonce = re.search(r''''csrfNonce': "([^"]+)"''', cast(str, csrf_response.text))
        if nonce:
            headers['CSRF-Token'] = nonce.group(1)
            if 'data' in kwargs:
                kwargs['data']['nonce'] = nonce.group(1)
        else:
            error('Failed to extract nonce.')

    if 'json' in kwargs:
        headers['Content-Type'] = 'application/json'
        kwargs['data'] = json.dumps(kwargs.pop('json'))

    try:
        if auth:
            kwargs.setdefault('allow_redirects', False)
        response = session.request(method, url, headers=headers, **kwargs)
    except Exception as e:
        error(f'Request failed: {e}')
    if auth and response.is_redirect:
        error('Session expired, please login again.')
    return response
