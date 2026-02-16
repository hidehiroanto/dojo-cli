"""
Handles installing, updating, and launching Zed.
"""

from io import BytesIO
import gzip
import json
import os
from pathlib import Path
from shutil import which
import requests
import subprocess
import sys
import tarfile
import tempfile

from .client import get_remote_client
from .config import load_user_config
from .http import request
from .install import homebrew_install, uv_install, wax_install, zerobrew_install
from .log import error, info, success, warn
from .remote import run_cmd, upload_file

HOME_DIR_MAX_SIZE = 1_000_000_000
LOCAL_BIN_DIR = Path('~/.local/bin').expanduser()

ZED_ARCH = 'zed-remote-server-linux-x86_64'
ZED_DOCS_URL = 'https://zed.dev/docs/remote-development'
ZED_INSTALL_URL = 'https://zed.dev/install.sh'
ZED_RELEASES_URL = 'https://api.github.com/repos/zed-industries/zed/releases'
ZED_SETTINGS_PATH = Path('~/.config/zed/settings.json').expanduser()

RUFF_ARCH = 'ruff-x86_64-unknown-linux-gnu'
RUFF_LATEST_URL = 'https://api.github.com/repos/astral-sh/ruff/releases/latest'
TY_ARCH = 'ty-x86_64-unknown-linux-gnu'
TY_LATEST_URL = 'https://api.github.com/repos/astral-sh/ty/releases/latest'

def install_zed():
    package_manager = load_user_config()['package_manager'][sys.platform]
    if sys.platform in ['darwin', 'linux']:
        # TODO: add support for other package managers
        if package_manager == 'homebrew':
            homebrew_install(casks=['zed'])
        elif package_manager == 'wax':
            wax_install(casks=['zed'])
        elif package_manager == 'zerobrew':
            zerobrew_install(casks=['zed'])
        else:
            # This just reinstalls Zed, it's easier than checking GitHub for the latest version
            subprocess.run(requests.get(ZED_INSTALL_URL).text, shell=True)
    elif sys.platform == 'win32':
        error('Windows is not yet supported.')
    else:
        error('Your OS is not yet supported.')

def install_lang_servers(lang_servers: list[str]):
    package_manager = load_user_config()['package_manager'][sys.platform]
    if sys.platform in ['darwin', 'linux']:
        # TODO: add support for other package managers
        if package_manager == 'homebrew':
            homebrew_install(lang_servers)
        elif package_manager == 'wax':
            wax_install(lang_servers)
        elif package_manager == 'zerobrew':
            zerobrew_install(lang_servers)
        else:
            uv_install(tools=lang_servers)
    elif sys.platform == 'win32':
        error('Windows is not yet supported.')
    else:
        error('Your OS is not yet supported.')

def load_zed_settings() -> tuple[dict, list[str]]:
    if ZED_SETTINGS_PATH.is_file():
        zed_settings_lines = ZED_SETTINGS_PATH.read_text().splitlines()
        comment_list = [line for line in zed_settings_lines if line.startswith('//')]
        return json.loads(''.join(line for line in zed_settings_lines if not line.startswith('//'))), comment_list

    return {}, []

def save_zed_settings(zed_settings: dict, comment_list: list[str]):
    ZED_SETTINGS_PATH.parent.mkdir(0o755, True, True)
    comments = ''.join(comment + '\n' for comment in comment_list)
    ZED_SETTINGS_PATH.write_text(comments + json.dumps(zed_settings, indent=2, sort_keys=True))

def check_lang_server_settings(lang_servers: list[str]):
    zed_settings, comment_list = load_zed_settings()

    # TODO: Switch to deep merge
    if not isinstance(zed_settings.get('languages'), dict):
        zed_settings['languages'] = {}
    if not isinstance(zed_settings['languages'].get('Python'), dict):
        zed_settings['languages']['Python'] = {}
    if not isinstance(zed_settings['languages']['Python'].get('language_servers'), list):
        zed_settings['languages']['Python']['language_servers'] = []

    if not all(lang_server in zed_settings['languages']['Python']['language_servers'] for lang_server in lang_servers):
        for lang_server in lang_servers:
            if lang_server not in zed_settings['languages']['Python']['language_servers']:
                zed_settings['languages']['Python']['language_servers'].append(lang_server)

        save_zed_settings(zed_settings, comment_list)

def upload_zed_server():
    client = get_remote_client()
    echo_query = run_cmd('echo $HOME', True) or b'/home/hacker'
    home_dir = Path(echo_query.strip().decode())
    zed_server_dir = home_dir / '.zed_server'
    client.makedirs(str(zed_server_dir))
    zed_old_versions = client.listdir(str(zed_server_dir))

    if sys.platform in ['darwin', 'linux']:
        zed_cli = Path(which('zed') or LOCAL_BIN_DIR / 'zed')
        if not zed_cli.is_file() or not zed_cli.is_symlink():
            error('Please install the Zed CLI first.')
        zed_root = zed_cli.resolve().parent.parent
        zed_app = zed_root / ('MacOS/zed' if sys.platform == 'darwin' else 'libexec/zed-editor')
    elif sys.platform == 'win32':
        error(f'Windows is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')
    else:
        error(f'Your OS is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')

    if not zed_app.is_file():
        error(f'Please install Zed first: [bold cyan]curl -f {ZED_INSTALL_URL} | sh[/].')
    zed_system_specs = subprocess.run([zed_app, '--system-specs'], capture_output=True).stdout
    zed_semver = zed_system_specs.split()[6].decode()
    zed_server = f'zed-remote-server-stable-{zed_semver[1:]}'

    info(f'Installed versions of zed-remote-server: {zed_old_versions}')
    info(f'Installed version of local Zed binary: [bold cyan]{zed_semver}[/]')

    if zed_server not in zed_old_versions:
        info('Updating zed-remote-server...')

        zed_version = zed_semver.split('+')[0]
        zed_releases = requests.get(ZED_RELEASES_URL).json()
        zed_release = next(release for release in zed_releases if release['tag_name'] == zed_version)
        zed_asset = next(asset for asset in zed_release['assets'] if ZED_ARCH in asset['browser_download_url'])
        zed_server_data = gzip.decompress(requests.get(zed_asset['browser_download_url']).content)

        # Check if enough disk space is available
        du_query = run_cmd(f'du -bs {home_dir} 2>/dev/null', True) or b'0'
        if len(zed_server_data) - client.getsize(str(zed_server_dir)) > HOME_DIR_MAX_SIZE - int(du_query.split()[0]):
            error('Not enough disk space to update zed-remote-server')

        for old_version in zed_old_versions:
            client.remove(str(zed_server_dir / old_version))

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(zed_server_data)
            temp_file.flush()
            upload_file(Path(temp_file.name), zed_server_dir / zed_server, False)

        client.chmod(str(zed_server_dir / zed_server), 0o755)
        success(f'Updated zed-remote-server to version [bold cyan]{zed_semver}[/]')

def upload_lang_server(lang_server: str, arch: str, latest_url: str):
    client = get_remote_client()
    echo_query = run_cmd('echo $HOME', True) or b'/home/hacker'
    home_dir = Path(echo_query.strip().decode())
    lang_dir = home_dir / '.local' / 'share' / 'zed' / 'languages'
    client.makedirs(str(lang_dir / lang_server))
    old_versions = client.listdir(str(lang_dir / lang_server))
    latest = requests.get(latest_url).json()

    info(f'Installed versions of {lang_server}: {old_versions}')
    info(f'Latest version of {lang_server}: [bold cyan]{latest['name']}[/]')

    if f'{lang_server}-{latest['name']}' not in old_versions:
        info(f'Updating {lang_server}...')

        lang_server_dir = lang_dir / lang_server / f'{lang_server}-{latest['name']}' / arch
        asset = next(asset for asset in latest['assets'] if arch in asset['browser_download_url'])
        targz = requests.get(asset['browser_download_url']).content

        with tarfile.open(fileobj=BytesIO(targz), mode='r:gz') as tar:
            tar_member = tar.extractfile(tar.getmember(f'{arch}/{lang_server}'))
            lang_server_data = tar_member.read() if tar_member else b''

        # Check if enough disk space is available
        du_query = run_cmd(f'du -bs {home_dir} 2>/dev/null', True) or b'0'
        if len(lang_server_data) - client.getsize(str(lang_dir / lang_server)) > HOME_DIR_MAX_SIZE - int(du_query.split()[0]):
            error('Not enough disk space to update language server')

        for old_version in old_versions:
            client.remove(str(lang_dir / lang_server / old_version))

        client.makedirs(str(lang_server_dir))
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(lang_server_data)
            temp_file.flush()
            upload_file(Path(temp_file.name), lang_server_dir / lang_server, False)

        client.chmod(str(lang_server_dir / lang_server), 0o755)
        success(f'Updated {lang_server} to version [bold cyan]{latest['name']}[/]')

def run_zed():
    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()

    zed = Path(which('zed') or LOCAL_BIN_DIR / 'zed')
    if not zed.is_file():
        error('Please upgrade zed to the latest version and ensure its parent directory is in PATH.')
    if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
        zed_argv = [zed, f'ssh://{ssh_config['Host']}{ssh_config['project_path']}']
    elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
        # TODO: Switch to deep merge
        zed_settings, comment_list = load_zed_settings()
        if not isinstance(zed_settings.get('ssh_connections'), list):
            zed_settings['ssh_connections'] = []
        if all(conn['nickname'] != ssh_config['Host'] and conn['host'] != ssh_config['HostName'] for conn in zed_settings['ssh_connections']):
            zed_settings['ssh_connections'].append({
                'host': ssh_config['HostName'],
                'port': ssh_config['Port'],
                'username': ssh_config['User'],
                'args': [
                    '-i', ssh_identity_file,
                    '-o', f'ServerAliveCountMax={ssh_config['ServerAliveCountMax']}',
                    '-o', f'ServerAliveInterval={ssh_config['ServerAliveInterval']}'
                ],
                'projects': [{'paths': [ssh_config['project_path']]}],
                'nickname': ssh_config['Host'],
                'upload_binary_over_ssh': True
            })
            save_zed_settings(zed_settings, comment_list)

        zed_argv = [
            zed,
            f'ssh://{ssh_config['User']}@{ssh_config['HostName']}:{ssh_config['Port']}{ssh_config['project_path']}'
        ]
    else:
        error('Something went wrong with the SSH config file or the SSH key, please make sure at least one is valid.')

    subprocess.run(zed_argv)

def init_zed(install: bool = False, use_lang_servers: bool = False):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('Challenge is not running, start a challenge first.')

    lang_servers = ['ruff', 'ty']

    if install:
        install_zed()
        if use_lang_servers:
            install_lang_servers(lang_servers)

    if sys.platform in ['darwin', 'linux']:
        upload_zed_server()
    elif sys.platform == 'win32':
        warn(f'Windows is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')
    else:
        warn(f'Your OS is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')

    if use_lang_servers:
        check_lang_server_settings(lang_servers)
        upload_lang_server('ruff', RUFF_ARCH, RUFF_LATEST_URL)
        upload_lang_server('ty', TY_ARCH, TY_LATEST_URL)

    run_zed()
