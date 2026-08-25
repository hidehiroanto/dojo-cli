"""Launch pwn.college workspace services."""

import subprocess
from urllib.parse import parse_qsl, urlencode, urlparse

from .constants import UNAME_SYSTEM, XDG_BIN_HOME
from .http import request
from .install import require_executable, run_install_script
from .log import error

TERMINAL_BROWSER_INSTALL_URL = 'https://terminal-browser.sh/install'


def install_terminal_browser():
    """Install terminal-browser using its official installer."""
    if UNAME_SYSTEM not in ['Darwin', 'Linux']:
        error(f'terminal-browser installation is not supported on {UNAME_SYSTEM}.')
    run_install_script('terminal-browser', TERMINAL_BROWSER_INSTALL_URL)


def fetch_workspace_url(service: str) -> str:
    """Fetch a fresh capability URL for an active workspace service."""
    response = request('/workspace', params={'service': service})

    if not response.ok:
        error(f'Workspace API returned HTTP {response.status_code}.')

    try:
        result = response.json()
    except ValueError:
        error('Workspace API returned invalid JSON.')

    if not isinstance(result, dict):
        error('Workspace API returned an invalid response.')

    if not result.get('success'):
        error(result.get('error', f'Could not open the {service} workspace.'))

    if result.get('active') is not True:
        error('No active challenge session; start a challenge first.')

    iframe_src = result.get('iframe_src')
    if not isinstance(iframe_src, str):
        error('Workspace API did not return a capability URL.')

    parsed = urlparse(iframe_src)
    hostname = parsed.hostname or ''
    trusted_host = (
        hostname == 'workspace.pwn.college'
        or hostname.endswith('-workspace.pwn.college')
    )

    if parsed.scheme != 'https' or not trusted_host:
        error('Workspace API returned an untrusted capability URL.')

    if service == 'desktop':
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query = [
            (key, 'scale' if key == 'resize' else value)
            for key, value in query
        ]
        if not any(key == 'resize' for key, _ in query):
            query.append(('resize', 'scale'))
        iframe_src = parsed._replace(query=urlencode(query)).geturl()

    return iframe_src


def open_workspace(service: str) -> None:
    """Open an active workspace service in terminal-browser."""
    terminal_browser = require_executable(
        'terminal-browser',
        [XDG_BIN_HOME / 'terminal-browser'],
        installer=install_terminal_browser if UNAME_SYSTEM in ['Darwin', 'Linux'] else None,
        method='the official installer',
    )

    workspace_url = fetch_workspace_url(service)
    completed = subprocess.run([
        terminal_browser,
        'open',
        workspace_url,
        '--no-shortcuts',
        '--allow-clipboard-read',
    ], check=False)

    if completed.returncode:
        raise SystemExit(completed.returncode)


def open_tode() -> None:
    """Open the active Code workspace in terminal-browser."""
    open_workspace('code')


def open_desktop() -> None:
    """Open the active Desktop workspace in terminal-browser."""
    open_workspace('desktop')
