"""Handles installing, updating, and launching Zed."""

import gzip
import json
import os
import re
import secrets
import subprocess
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

import niquests
import yaml

from .client import get_remote_client
from .config import load_user_config
from .constants import UNAME_SYSTEM, XDG_BIN_HOME, XDG_CONFIG_HOME
from .http import request
from .install import (
    configured_package_manager,
    confirm_install,
    find_executable,
    homebrew_install,
    nanobrew_install,
    require_executable,
    run_install_script,
    uv_install,
    wax_install,
    zerobrew_install,
)
from .log import error, info, success, warn
from .remote import run_cmd, upload_file

HOME_DIR_MAX_SIZE = 1_000_000_000

ZED_DOCS_URL = 'https://zed.dev/docs/remote-development'
ZED_INSTALL_URL = 'https://zed.dev/install.sh'
ZED_RELEASES_URL = 'https://api.github.com/repos/zed-industries/zed/releases'
ZED_SETTINGS_PATH = XDG_CONFIG_HOME.expanduser() / 'zed' / 'settings.json'

RUFF_LATEST_URL = 'https://api.github.com/repos/astral-sh/ruff/releases/latest'
TY_LATEST_URL = 'https://api.github.com/repos/astral-sh/ty/releases/latest'

ARCHITECTURES = {
    'x86_64': ('x86_64', 'x86_64-unknown-linux-gnu'),
    'amd64': ('x86_64', 'x86_64-unknown-linux-gnu'),
}

def get_remote_architecture() -> tuple[str, str]:
    """Return Zed and Rust target names for the remote architecture."""
    result = run_cmd('uname -m', capture_output=True, pty=False)
    architecture = result.stdout.strip().decode(errors='replace')
    if result.returncode or architecture not in ARCHITECTURES:
        error(f'Remote architecture {architecture or 'unknown'} is not supported yet.')
    return ARCHITECTURES[architecture]

def upload_remote_binary(client, data: bytes, destination: Path):
    """Atomically upload an executable to the remote host."""
    client.makedirs(str(destination.parent))
    temporary = destination.with_name(f'.{destination.name}.{secrets.token_hex(8)}.tmp')
    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(data)
            temp_file.flush()
            upload_file(Path(temp_file.name), temporary, False)
        client.chmod(str(temporary), 0o755)
        client.rename(str(temporary), str(destination))
    finally:
        if client.is_file(str(temporary)):
            client.remove(str(temporary))

def install_zed():
    package_manager = configured_package_manager()
    if UNAME_SYSTEM in ['Darwin', 'Linux']:
        # TODO: add support for other package managers
        if package_manager == 'homebrew':
            homebrew_install(casks=['zed'])
        elif package_manager == 'nanobrew':
            nanobrew_install(casks=['zed'])
        elif package_manager == 'wax':
            wax_install(casks=['zed'])
        elif package_manager == 'zerobrew':
            zerobrew_install(casks=['zed'])
        else:
            run_install_script('Zed', ZED_INSTALL_URL)
    elif UNAME_SYSTEM == 'Windows':
        error('Windows is not yet supported.')
    else:
        error('Your OS is not yet supported.')

def install_lang_servers(lang_servers: list[str]):
    package_manager = configured_package_manager()
    if UNAME_SYSTEM in ['Darwin', 'Linux']:
        # TODO: add support for other package managers
        if package_manager == 'homebrew':
            homebrew_install(lang_servers, skip_update=True)
        elif package_manager == 'nanobrew':
            nanobrew_install(lang_servers, skip_update=True)
        elif package_manager == 'wax':
            wax_install(lang_servers, skip_update=True)
        elif package_manager == 'zerobrew':
            zerobrew_install(lang_servers, skip_update=True)
        else:
            uv_install(tools=lang_servers)
    elif UNAME_SYSTEM == 'Windows':
        error('Windows is not yet supported.')
    else:
        error('Your OS is not yet supported.')

def load_zed_settings() -> tuple[dict, list[str]]:
    if ZED_SETTINGS_PATH.is_file():
        try:
            zed_settings_lines = ZED_SETTINGS_PATH.read_text().splitlines()
            comment_list = [line for line in zed_settings_lines if line.startswith('//')]
            settings_text = '\n'.join(line for line in zed_settings_lines if not line.startswith('//'))
            zed_settings = yaml.safe_load(settings_text) or {}
        except (OSError, yaml.YAMLError) as exc:
            error(f'Could not parse Zed settings: {exc}')
        if not isinstance(zed_settings, dict):
            error('Zed settings must contain an object.')
        return zed_settings, comment_list

    return {}, []

def find_zed_cli() -> Path | None:
    """Find the Zed CLI on PATH or in the user executable directory."""
    return find_executable('zed', [XDG_BIN_HOME / 'zed'])

def require_zed_cli() -> Path:
    """Resolve Zed, installing it after confirmation if needed."""
    return require_executable(
        'zed',
        [XDG_BIN_HOME / 'zed'],
        display_name='Zed',
        installer=install_zed if UNAME_SYSTEM in ['Darwin', 'Linux'] else None,
        method=configured_package_manager() if UNAME_SYSTEM in ['Darwin', 'Linux'] else None,
    )

def save_zed_settings(zed_settings: dict, comment_list: list[str]):
    ZED_SETTINGS_PATH.parent.mkdir(0o755, True, True)
    comments = ''.join(comment + '\n' for comment in comment_list)
    mode = ZED_SETTINGS_PATH.stat().st_mode & 0o777 if ZED_SETTINGS_PATH.exists() else 0o600
    with tempfile.NamedTemporaryFile('w', dir=ZED_SETTINGS_PATH.parent, delete=False) as temp_file:
        temp_file.write(comments + json.dumps(zed_settings, indent=2, sort_keys=True))
        temporary = Path(temp_file.name)
    try:
        temporary.chmod(mode)
        temporary.replace(ZED_SETTINGS_PATH)
    finally:
        temporary.unlink(missing_ok=True)

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
    echo_result = run_cmd('echo $HOME', capture_output=True, pty=False)
    echo_query = echo_result.stdout if echo_result.returncode == 0 and echo_result.stdout else b'/home/hacker'
    home_dir = Path(echo_query.strip().decode())
    zed_arch, _ = get_remote_architecture()
    zed_server_dir = home_dir / '.zed_server'
    client.makedirs(str(zed_server_dir))
    zed_old_versions = client.listdir(str(zed_server_dir))

    if UNAME_SYSTEM in ['Darwin', 'Linux']:
        zed_cli = require_zed_cli().resolve()

        if UNAME_SYSTEM == 'Darwin':
            zed_app = zed_cli.parent / 'zed'
        elif UNAME_SYSTEM == 'Linux':
            zed_app = zed_cli.parent.parent / 'libexec' / 'zed-editor'
    elif UNAME_SYSTEM == 'Windows':
        error(f'Windows is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')
    else:
        error(f'Your OS is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')

    if not zed_app.is_file():
        confirm_install('Zed', configured_package_manager())
        install_zed()
        zed_cli = require_zed_cli().resolve()
        zed_app = zed_cli.parent / 'zed' if UNAME_SYSTEM == 'Darwin' else zed_cli.parent.parent / 'libexec' / 'zed-editor'
        if not zed_app.is_file():
            error('Zed is still missing after installation.')
    zed_system_specs = subprocess.run([str(zed_app), '--system-specs'], check=True, capture_output=True).stdout
    version_match = re.search(rb'^Zed:\s+(v\d+\.\d+\.\d+(?:[-+][^\s]+)?)', zed_system_specs, re.MULTILINE)
    if version_match is None:
        error('Could not determine the installed Zed version.')
    zed_semver = version_match.group(1).decode()
    zed_server = f'zed-remote-server-stable-{zed_semver[1:]}'

    info(f'Installed versions of zed-remote-server: {zed_old_versions}')
    info(f'Installed version of local Zed binary: [b cyan]{zed_semver}[/]')

    if zed_server not in zed_old_versions:
        info('Updating zed-remote-server...')

        zed_version = zed_semver.split('+')[0]
        zed_releases = niquests.get(ZED_RELEASES_URL).json()
        zed_release = next(release for release in zed_releases if release['tag_name'] == zed_version)
        zed_asset_name = f'zed-remote-server-linux-{zed_arch}'
        zed_asset = next(asset for asset in zed_release['assets'] if zed_asset_name in asset['browser_download_url'])
        zed_server_data = gzip.decompress(niquests.get(zed_asset['browser_download_url']).content or b'')

        # Check if enough disk space is available
        du_result = run_cmd(f'du -bs {home_dir} 2>/dev/null', capture_output=True, pty=False)
        du_query = du_result.stdout if du_result.returncode == 0 and du_result.stdout else b'0'
        if len(zed_server_data) - client.getsize(str(zed_server_dir)) > HOME_DIR_MAX_SIZE - int(du_query.split()[0]):
            error('Not enough disk space to update zed-remote-server')

        upload_remote_binary(client, zed_server_data, zed_server_dir / zed_server)

        for old_version in zed_old_versions:
            if old_version != zed_server:
                client.remove(str(zed_server_dir / old_version))
        success(f'Updated zed-remote-server to version [b cyan]{zed_semver}[/]')

def upload_lang_server(lang_server: str, arch: str, latest_url: str):
    client = get_remote_client()
    echo_result = run_cmd('echo $HOME', capture_output=True, pty=False)
    echo_query = echo_result.stdout if echo_result.returncode == 0 and echo_result.stdout else b'/home/hacker'
    home_dir = Path(echo_query.strip().decode())
    lang_dir = home_dir / '.local' / 'share' / 'zed' / 'languages'
    client.makedirs(str(lang_dir / lang_server))
    old_versions = client.listdir(str(lang_dir / lang_server))
    latest = niquests.get(latest_url).json()

    info(f'Installed versions of {lang_server}: {old_versions}')
    info(f'Latest version of {lang_server}: [b cyan]{latest['name']}[/]')

    if f'{lang_server}-{latest['name']}' not in old_versions:
        info(f'Updating {lang_server}...')

        lang_server_dir = lang_dir / lang_server / f'{lang_server}-{latest['name']}' / arch
        asset = next(asset for asset in latest['assets'] if arch in asset['browser_download_url'])
        targz = niquests.get(asset['browser_download_url']).content or b''

        with tarfile.open(fileobj=BytesIO(targz), mode='r:gz') as tar:
            tar_member = tar.extractfile(tar.getmember(f'{arch}/{lang_server}'))
            lang_server_data = tar_member.read() if tar_member else b''

        # Check if enough disk space is available
        du_result = run_cmd(f'du -bs {home_dir} 2>/dev/null', capture_output=True, pty=False)
        du_query = du_result.stdout if du_result.returncode == 0 and du_result.stdout else b'0'
        if len(lang_server_data) - client.getsize(str(lang_dir / lang_server)) > HOME_DIR_MAX_SIZE - int(du_query.split()[0]):
            error('Not enough disk space to update language server')

        upload_remote_binary(client, lang_server_data, lang_server_dir / lang_server)

        for old_version in old_versions:
            if old_version != f'{lang_server}-{latest['name']}':
                client.remove(str(lang_dir / lang_server / old_version))
        success(f'Updated {lang_server} to version [b cyan]{latest['name']}[/]')

def run_zed():
    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()

    zed_cli = require_zed_cli()
    if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
        zed_args = [zed_cli, f'ssh://{ssh_config['Host']}{ssh_config['project_path']}']
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

        zed_args = [
            zed_cli,
            f'ssh://{ssh_config['User']}@{ssh_config['HostName']}:{ssh_config['Port']}{ssh_config['project_path']}'
        ]
    else:
        error('Something went wrong with the SSH config file or the SSH key, please make sure at least one is valid.')

    completed = subprocess.run([str(arg) for arg in zed_args], check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)

def init_zed(install: bool = False, use_lang_servers: bool = False):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('Challenge is not running, start a challenge first.')

    lang_servers = ['ruff', 'ty']

    if install:
        install_zed()
        if find_zed_cli() is None:
            error('Zed is still missing after installation.')
        if use_lang_servers:
            install_lang_servers(lang_servers)
    else:
        require_zed_cli()

    if UNAME_SYSTEM in ['Darwin', 'Linux']:
        upload_zed_server()
    elif UNAME_SYSTEM == 'Windows':
        warn(f'Windows is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')
    else:
        warn(f'Your OS is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')

    if use_lang_servers:
        _, tool_arch = get_remote_architecture()
        check_lang_server_settings(lang_servers)
        upload_lang_server('ruff', f'ruff-{tool_arch}', RUFF_LATEST_URL)
        upload_lang_server('ty', f'ty-{tool_arch}', TY_LATEST_URL)

    run_zed()
