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

from .config import load_user_config
from .http import request
from .log import error, info, success, warn
from .remote import run_cmd, ssh_getsize, ssh_listdir, ssh_mkdir, ssh_remove, ssh_rmdir, upload_file

HOME_DIR_MAX_SIZE = 1_000_000_000
LOCAL_BIN_DIR = Path('~/.local/bin').expanduser()
CARGO_BIN_DIR = Path('~/.cargo/bin').expanduser()
RUSTUP_INSTALL_URL = 'https://sh.rustup.rs'

HOMEBREW_BIN_DIR = Path('/opt/homebrew/bin')
HOMEBREW_INSTALL_URL = 'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh'
ZEROBREW_BIN_DIR = Path('/opt/zerobrew/prefix/bin')
ZEROBREW_GITHUB_URL = 'https://github.com/lucasgelfond/zerobrew'
ZEROBREW_INSTALL_URL = 'https://zerobrew.rs/install'

ZED_ARCH = 'zed-remote-server-linux-x86_64'
ZED_DOCS_URL = 'https://zed.dev/docs/remote-development'
ZED_INSTALL_URL = 'https://zed.dev/install.sh'
ZED_RELEASES_URL = 'https://api.github.com/repos/zed-industries/zed/releases'
ZED_SETTINGS_PATH = Path('~/.config/zed/settings.json').expanduser()

RUFF_ARCH = 'ruff-x86_64-unknown-linux-gnu'
RUFF_LATEST_URL = 'https://api.github.com/repos/astral-sh/ruff/releases/latest'
TY_ARCH = 'ty-x86_64-unknown-linux-gnu'
TY_LATEST_URL = 'https://api.github.com/repos/astral-sh/ty/releases/latest'
UV_INSTALL_URL = 'https://astral.sh/uv/install.sh'

def homebrew_install(casks: list[str] = [], formulae: list[str] = []):
    """Install Homebrew casks and formulae."""

    brew = Path(which('brew') or HOMEBREW_BIN_DIR / 'brew')
    if not brew.is_file():
        info('Installing Homebrew...')
        subprocess.run(['bash', '-c', requests.get(HOMEBREW_INSTALL_URL).text])
    else:
        subprocess.run([brew, 'update'])

    if casks:
        subprocess.run([brew, 'install', '--cask'] + casks)
    if formulae:
        subprocess.run([brew, 'install'] + formulae)

def scoop_install():
    # Requires PowerShell
    # Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
    # Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
    # scoop bucket add main
    # scoop bucket add extras
    # scoop install extras/zed
    # scoop install main/ruff
    # scoop install main/ty
    pass

# Avoid using for now, wax can't detect installed casks
# `wax install --cask zed` (if zed is already installed?) may lead to `IO error: Permission denied (os error 13)`
# Using wax to uninstall and reinstall ruff or ty may lead to `IO error: File exists (os error 17)`
def wax_install(casks: list[str] = [], formulae: list[str] = []):
    """Install Homebrew casks and formulae using the experimental Wax package manager written in Rust."""

    cargo = Path(which('cargo') or CARGO_BIN_DIR / 'cargo')
    if not cargo.is_file():
        info('Installing Rust...')
        subprocess.run(requests.get(RUSTUP_INSTALL_URL).text, shell=True)

    wax = Path(which('wax') or CARGO_BIN_DIR / 'wax')
    if not wax.is_file():
        info('Installing Wax...')
        subprocess.run([cargo, 'install', 'waxpkg'])
    else:
        subprocess.run([wax, 'update', '-s'])

    if casks:
        subprocess.run([wax, 'install', '--cask'] + casks)
    if formulae:
        subprocess.run([wax, 'install'] + formulae)

def zerobrew_install(casks: list[str] = [], formulae: list[str] = []):
    """Install Homebrew casks and formulae using the experimental Zerobrew package manager written in Rust."""

    cargo = Path(which('cargo') or CARGO_BIN_DIR / 'cargo')
    if not cargo.is_file():
        info('Installing Rust...')
        subprocess.run(requests.get(RUSTUP_INSTALL_URL).text, shell=True)

    # zerobrew v0.1.1 is broken, cargo install from source instead for now
    # zb = Path(which('zb') or LOCAL_BIN_DIR / 'zb')
    zb = Path(which('zb') or CARGO_BIN_DIR / 'zb')
    if not zb.is_file():
        info('Installing Zerobrew...')
        # subprocess.run(requests.get(ZEROBREW_INSTALL_URL).text, shell=True)
        subprocess.run(['cargo', 'install', '--git', ZEROBREW_GITHUB_URL])
        # if zb != CARGO_BIN_DIR / 'zb':
        #     if zb.is_file():
        #         zb.unlink()
        #     zb.symlink_to(CARGO_BIN_DIR / 'zb')

    if casks:
        # Fall back to homebrew for now
        # TODO: replace this when zerobrew supports casks
        homebrew_install(casks)
    if formulae:
        subprocess.run([zb, 'install'] + formulae)

# TODO: add support for other package managers

def upgrade_zed_client(upgrade_lang_servers: bool = False):
    package_manager = load_user_config()['package_manager'][sys.platform]
    if sys.platform in ['darwin', 'linux']:
        # TODO: add support for other package managers
        if package_manager == 'homebrew':
            homebrew_install(['zed'], ['ruff', 'ty'] if upgrade_lang_servers else [])

        elif package_manager == 'wax':
            wax_install(['zed'], ['ruff', 'ty'] if upgrade_lang_servers else [])

        elif package_manager == 'zerobrew':
            zerobrew_install(['zed'], ['ruff', 'ty'] if upgrade_lang_servers else [])

        else:
            # This just reinstalls Zed, it's easier than checking GitHub for the latest version
            subprocess.run(requests.get(ZED_INSTALL_URL).text, shell=True)

            if upgrade_lang_servers:
                uv = Path(which('uv') or LOCAL_BIN_DIR / 'uv')
                if not uv.is_file():
                    info('Installing uv...')
                    subprocess.run(requests.get(UV_INSTALL_URL).text, shell=True)
                else:
                    subprocess.run([uv, 'self', 'update'])

                subprocess.run([uv, 'tool', 'install', '-U', 'ruff'])
                subprocess.run([uv, 'tool', 'install', '-U', 'ty'])
    elif sys.platform == 'win32':
        # TODO: add Windows support
        error('Windows is not yet supported.')
    else:
        error('Your operating system is not yet supported.')

def load_zed_settings() -> tuple[dict, list[str]]:
    if ZED_SETTINGS_PATH.is_file():
        zed_settings_lines = ZED_SETTINGS_PATH.read_text().splitlines()
        comment_list = [line for line in zed_settings_lines if line.startswith('//')]
        return json.loads(''.join(line for line in zed_settings_lines if not line.startswith('//'))), comment_list

    return {}, []

def save_zed_settings(zed_settings: dict, comment_list: list[str]):
    ZED_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    comments = ''.join(comment + '\n' for comment in comment_list)
    ZED_SETTINGS_PATH.write_text(comments + json.dumps(zed_settings, indent=2, sort_keys=True))

def check_lang_server_settings():
    zed_settings, comment_list = load_zed_settings()

    # TODO: Switch to deep merge
    if not isinstance(zed_settings.get('languages'), dict):
        zed_settings['languages'] = {}
    if not isinstance(zed_settings['languages'].get('Python'), dict):
        zed_settings['languages']['Python'] = {}
    if not isinstance(zed_settings['languages']['Python'].get('language_servers'), list):
        zed_settings['languages']['Python']['language_servers'] = []

    if not all(lang_server in zed_settings['languages']['Python']['language_servers'] for lang_server in ['ruff', 'ty']):
        for lang_server in ['ruff', 'ty']:
            if lang_server not in zed_settings['languages']['Python']['language_servers']:
                zed_settings['languages']['Python']['language_servers'].append(lang_server)

        save_zed_settings(zed_settings, comment_list)

def upload_zed_server():
    echo_query = run_cmd('echo $HOME', True) or b'/home/hacker'
    home_dir = Path(echo_query.strip().decode())
    zed_server_dir = home_dir / '.zed_server'
    zed_old_versions = ssh_listdir(zed_server_dir)

    if sys.platform in ['darwin', 'linux']:
        zed_cli = Path(which('zed') or LOCAL_BIN_DIR / 'zed')
        if not zed_cli.is_file() or not zed_cli.is_symlink():
            error('Please install the Zed CLI first.')
        zed_root = zed_cli.resolve().parent.parent
        zed_app = zed_root / ('MacOS/zed' if sys.platform == 'darwin' else 'libexec/zed-editor')
    elif sys.platform == 'win32':
        error('Windows is not yet supported. Please consult the relevant resources to upload the server manually.')
    else:
        error('Your operating system is not yet supported. Please consult the relevant resources to upload the server manually.')

    if not zed_app.is_file():
        error(f'Please install Zed first: [bold cyan]curl -f {ZED_INSTALL_URL} | sh[/].')
    zed_system_specs = subprocess.run([zed_app, '--system-specs'], capture_output=True).stdout
    zed_semver = zed_system_specs.split()[6].decode()

    info(f'Installed versions of zed-remote-server: {zed_old_versions}')
    info(f'Installed version of local Zed binary: {zed_semver}')

    zed_server = f'zed-remote-server-stable-{zed_semver[1:]}'
    if zed_server not in zed_old_versions:
        info('Updating zed-remote-server...')

        zed_version = zed_semver.split('+')[0]
        zed_releases = requests.get(ZED_RELEASES_URL).json()
        zed_release = next(release for release in zed_releases if release['tag_name'] == zed_version)
        zed_asset = next(asset for asset in zed_release['assets'] if ZED_ARCH in asset['browser_download_url'])
        zed_server_data = gzip.decompress(requests.get(zed_asset['browser_download_url']).content)

        # Check if enough disk space is available
        du_query = run_cmd(f'du -bs {home_dir} 2>/dev/null', True) or b'0' # ssh_getsize(home_dir)
        if len(zed_server_data) - ssh_getsize(zed_server_dir) > HOME_DIR_MAX_SIZE - int(du_query.split()[0]):
            error('Not enough disk space to update zed-remote-server')

        for old_version in zed_old_versions:
            ssh_remove(zed_server_dir / old_version)

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(zed_server_data)
            temp_file.flush()
            temp_path = Path(temp_file.name)
            temp_path.chmod(0o755)
            upload_file(temp_path, zed_server_dir / zed_server)

        success(f'Updated zed-remote-server to version {zed_semver}')

def upload_lang_server(lang_server: str, arch: str, latest_url: str):
    echo_query = run_cmd('echo $HOME', True) or b'/home/hacker'
    home_dir = Path(echo_query.strip().decode())
    lang_dir = home_dir / '.local' / 'share' / 'zed' / 'languages'
    old_versions = ssh_listdir(lang_dir / lang_server)
    latest = requests.get(latest_url).json()

    info(f'Installed versions of {lang_server}: {old_versions}')
    info(f'Latest version of {lang_server}: {latest['name']}')

    if f'{lang_server}-{latest['name']}' not in old_versions:
        info(f'Updating {lang_server}...')

        lang_server_dir = lang_dir / lang_server / f'{lang_server}-{latest['name']}' / arch
        asset = next(asset for asset in latest['assets'] if arch in asset['browser_download_url'])
        targz = requests.get(asset['browser_download_url']).content

        with tarfile.open(fileobj=BytesIO(targz), mode='r:gz') as tar:
            tar_member = tar.extractfile(tar.getmember(f'{arch}/{lang_server}'))
            lang_server_data = tar_member.read() if tar_member else b''

        # Check if enough disk space is available
        du_query = run_cmd(f'du -bs {home_dir} 2>/dev/null', True) or b'0' # ssh_getsize(home_dir)
        if len(lang_server_data) - ssh_getsize(lang_dir / lang_server) > HOME_DIR_MAX_SIZE - int(du_query.split()[0]):
            error('Not enough disk space to update language server')

        for old_version in old_versions:
            ssh_rmdir(lang_dir / lang_server / old_version)
        ssh_mkdir(lang_server_dir)

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(lang_server_data)
            temp_file.flush()
            temp_path = Path(temp_file.name)
            temp_path.chmod(0o755)
            upload_file(temp_path, lang_server_dir / lang_server)

        success(f'Updated {lang_server} to version {latest['name']}')

def run_zed_client():
    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

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

def init_zed(upgrade_zed: bool = False, use_lang_servers: bool = False):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('Challenge is not running, start a challenge first.')

    if upgrade_zed:
        upgrade_zed_client(use_lang_servers)

    if sys.platform in ['darwin', 'linux']:
        upload_zed_server()
    elif sys.platform == 'win32':
        warn(f'Windows is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')
    else:
        warn(f'Your OS is not yet supported. Consult the relevant [link={ZED_DOCS_URL}]documentation[/] to upload the server.')

    if use_lang_servers:
        check_lang_server_settings()
        upload_lang_server('ruff', RUFF_ARCH, RUFF_LATEST_URL)
        upload_lang_server('ty', TY_ARCH, TY_LATEST_URL)

    run_zed_client()
