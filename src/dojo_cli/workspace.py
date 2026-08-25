"""Launch pwn.college workspace services."""

import html
import secrets
import subprocess
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from string import Template
from threading import Thread
from urllib.parse import parse_qsl, urlencode, urlparse

from .constants import UNAME_SYSTEM, XDG_BIN_HOME
from .http import request
from .install import require_executable, run_install_script
from .log import error

TERMINAL_BROWSER_INSTALL_URL = 'https://terminal-browser.sh/install'
WORKSPACE_PAGE = Template("""<!doctype html>
<html>
<head>
<meta charset='utf-8'>
<meta name='referrer' content='no-referrer'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>pwn.college workspace</title>
<style>
html, body, iframe { border: 0; height: 100%; margin: 0; padding: 0; width: 100%; }
iframe { display: block; }
</style>
</head>
<body>
<iframe src='$destination' allow='clipboard-read; clipboard-write'></iframe>
</body>
</html>
""")


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
    trusted_host = hostname == 'workspace.pwn.college' or hostname.endswith(
        '-workspace.pwn.college'
    )

    if parsed.scheme != 'https' or not trusted_host:
        error('Workspace API returned an untrusted capability URL.')

    if service == 'desktop':
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query = [(key, 'scale' if key == 'resize' else value) for key, value in query]
        if not any(key == 'resize' for key, _ in query):
            query.append(('resize', 'scale'))
        iframe_src = parsed._replace(query=urlencode(query)).geturl()

    return iframe_src


def workspace_handler(token: str, destination: str) -> type[BaseHTTPRequestHandler]:
    """Create a handler that embeds a capability without navigating to it."""
    page = WORKSPACE_PAGE.substitute(
        destination=html.escape(destination, quote=True),
    ).encode()

    class WorkspaceHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != f'/{token}':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Cache-Control', 'no-store')
            self.send_header(
                'Content-Security-Policy',
                "default-src 'none'; frame-src https://*.pwn.college; "
                "style-src 'unsafe-inline'",
            )
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Length', str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format, *args):
            pass

    return WorkspaceHandler


@contextmanager
def capability_page(destination: str):
    """Expose a capability inside a short-lived loopback page."""
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(
        ('127.0.0.1', 0), workspace_handler(token, destination)
    )
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/{token}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def open_workspace(service: str) -> None:
    """Open an active workspace service in terminal-browser."""
    terminal_browser = require_executable(
        'terminal-browser',
        [XDG_BIN_HOME / 'terminal-browser'],
        installer=install_terminal_browser
        if UNAME_SYSTEM in ['Darwin', 'Linux']
        else None,
        method='the official installer',
    )

    with capability_page(fetch_workspace_url(service)) as launch_url:
        completed = subprocess.run(
            [
                terminal_browser,
                'open',
                launch_url,
                '--no-shortcuts',
                '--allow-clipboard-read',
            ],
            check=False,
        )

    if completed.returncode:
        raise SystemExit(completed.returncode)


def open_tode() -> None:
    """Open the active Code workspace in terminal-browser."""
    open_workspace('code')


def open_desktop() -> None:
    """Open the active Desktop workspace in terminal-browser."""
    open_workspace('desktop')
