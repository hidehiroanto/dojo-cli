"""
Handles installing, updating, and launching Zed. I've only tested this on Mac OS so far.
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
from .log import error, info, success
from .remote import run_cmd, ssh_listdir, ssh_remove, transfer

# use zerobrew or wax instead of homebrew?
def homebrew_upgrade(formulae: list):
    """Upgrade Homebrew formulae. `formulae` is a list of formula names or formula tuples `(name, is_cask)`."""
    brew = Path(which('brew') or '/opt/homebrew/bin/brew')

    if not brew.is_file():
        info('Installing Homebrew first...')
        brew_url = 'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh'
        subprocess.run(['bash', '-c', requests.get(brew_url).text])

    subprocess.run([brew, 'update'])

    for formula in formulae:
        if isinstance(formula, str):
            formula = (formula, False)
        if not Path(which(formula[0]) or f'/opt/homebrew/bin/{formula[0]}').is_file():
            subprocess.run([brew, 'upgrade', '-g', formula[0]])
        else:
            subprocess.run([brew, 'install', '--cask', formula[0]] if formula[1] else [brew, 'install', formula[0]])

def upgrade_zed_client(upgrade_lang_servers: bool = False, use_package_manager: bool = True):
    if sys.platform in ['darwin', 'linux']:
        # TODO: add Linux package manager support
        if sys.platform == 'darwin' and use_package_manager:
            homebrew_upgrade([('zed', True), 'ruff', 'ty'] if upgrade_lang_servers else [('zed', True)])
        else:
            # This just reinstalls zed, I do not have a better way to upgrade it currently
            subprocess.run(['sh', '-c', requests.get('https://zed.dev/install.sh').text])
            if upgrade_lang_servers:
                # use uv?
                subprocess.run(['python3', '-m', 'pip', 'install', '-U', '--user', 'ruff', 'ty'])
    elif sys.platform == 'win32':
        # TODO: add Windows support
        error('Windows is not yet supported.')
    else:
        error('Your operating system is not yet supported.')

def load_zed_settings() -> tuple[dict, list[str]]:
    # I know this is the case for Mac and probably Linux, probably not for Windows
    zed_settings_path = Path('~/.config/zed/settings.json').expanduser()

    if zed_settings_path.is_file():
        zed_settings_lines = zed_settings_path.read_text().splitlines()
        comment_list = [line for line in zed_settings_lines if line.startswith('//')]
        return json.loads(''.join(line for line in zed_settings_lines if not line.startswith('//'))), comment_list

    return {}, []

def save_zed_settings(zed_settings: dict, comment_list: list[str]):
    # I know this is the case for Mac and probably Linux, probably not for Windows
    zed_settings_path = Path('~/.config/zed/settings.json').expanduser()
    zed_settings_path.parent.mkdir(parents=True, exist_ok=True)
    comments = ''.join(comment + '\n' for comment in comment_list)
    zed_settings_path.write_text(comments + json.dumps(zed_settings, indent=2, sort_keys=True))

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

def upload_lang_server(lang_server: str, home_dir: Path = Path('/home/hacker')):
    lang_dir = home_dir / '.local' / 'share' / 'zed' / 'languages'
    versions = ssh_listdir(lang_dir / lang_server)
    latest = requests.get(f'https://api.github.com/repos/astral-sh/{lang_server}/releases/latest').json()

    info(f'Installed versions of {lang_server}: {versions}')
    info(f'Latest version of {lang_server}: {latest['name']}')

    if f'{lang_server}-{latest['name']}' not in versions:
        info(f'Updating {lang_server}...')
        # Check if enough disk space is available?
        # if new_size - old_sizes > free_space == 1 GB - used_space:
        #     error('Not enough disk space to update language server')

        arch = f'{lang_server}-x86_64-unknown-linux-gnu'
        lang_server_dir = lang_dir / lang_server / f'{lang_server}-{latest['name']}' / arch
        asset = next(asset for asset in latest['assets'] if arch in asset['browser_download_url'])
        targz = requests.get(asset['browser_download_url']).content

        with tarfile.open(fileobj=BytesIO(targz), mode='r:gz') as tar:
            tar_member = tar.extractfile(tar.getmember(f'{arch}/{lang_server}'))
            lang_server_data = tar_member.read() if tar_member else b''

        for version in versions:
            # ssh_rmdir(lang_dir / lang_server / version)
            run_cmd(f'rm -r {lang_dir / lang_server / '*'}')
        run_cmd(f'mkdir -p {lang_server_dir}')

        with tempfile.NamedTemporaryFile() as f:
            Path(f.name).chmod(0o755)
            f.write(lang_server_data)
            f.flush()
            transfer(f.name, lang_server_dir / lang_server, True)

        success(f'Updated {lang_server} to version {latest['name']}')

def upload_zed_server(use_lang_servers: bool = False):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('Challenge is not running, start a challenge first.')

    echo_query = run_cmd('echo $HOME', True)
    home_dir = Path((echo_query or b'/home/hacker').strip().decode())
    zed_server_dir = home_dir / '.zed_server'
    zed_versions = ssh_listdir(zed_server_dir)

    if sys.platform in ['darwin', 'linux']:
        zed_cli = Path(which('zed') or '~/.local/bin/zed').expanduser()
        if not zed_cli.is_file() or not zed_cli.is_symlink():
            error('Please install the Zed CLI first.')
        zed_root = zed_cli.resolve().parent.parent
        zed_app = zed_root / ('MacOS/zed' if sys.platform == 'darwin' else 'libexec/zed-editor')
    elif sys.platform == 'win32':
        error('Windows is not yet supported. Please consult the relevant resources to upload the server manually.')
    else:
        error('Your operating system is not yet supported.')

    if not zed_app.is_file():
        error('Please install Zed first: [bold cyan]curl -f https://zed.dev/install.sh | sh[/].')
    zed_system_specs = subprocess.run([zed_app, '--system-specs'], capture_output=True).stdout
    zed_semver = zed_system_specs.split()[6].decode()

    info(f'Installed versions of zed-remote-server: {zed_versions}')
    info(f'Installed version of local Zed binary: {zed_semver}')

    zed_server = f'zed-remote-server-stable-{zed_semver[1:]}'
    if zed_server not in zed_versions:
        info('Updating zed-remote-server...')
        # Check if enough disk space is available?
        # if new_size - old_sizes > free_space == 1 GB - used_space:
        #     error('Not enough disk space to update zed-remote-server')

        zed_version = zed_semver.split('+')[0]

        zed_releases = requests.get('https://api.github.com/repos/zed-industries/zed/releases').json()
        zed_release = next(release for release in zed_releases if release['tag_name'] == zed_version)
        zed_arch = 'zed-remote-server-linux-x86_64'
        zed_asset = next(asset for asset in zed_release['assets'] if zed_arch in asset['browser_download_url'])
        zed_server_data = gzip.decompress(requests.get(zed_asset['browser_download_url']).content)

        for version in zed_versions:
            ssh_remove(zed_server_dir / version)

        with tempfile.NamedTemporaryFile() as f:
            Path(f.name).chmod(0o755)
            f.write(zed_server_data)
            f.flush()
            transfer(f.name, zed_server_dir / zed_server, True)

        success(f'Updated zed-remote-server to version {zed_semver}')

    if use_lang_servers:
        upload_lang_server('ruff', home_dir)
        upload_lang_server('ty', home_dir)

def run_zed_client():
    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

    zed = Path(which('zed') or '~/.local/bin/zed').expanduser()
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

    if use_lang_servers:
        check_lang_server_settings()

    upload_zed_server(use_lang_servers)
    run_zed_client()
