"""Handles installing, updating, and launching SSHFS and code editors."""

# TODO: Add more package managers, Windows support?
# TODO: Move mount stuff to client.py or mount.py?

import os
import subprocess
from pathlib import Path

import mfusepy as fuse

from .client import RemoteClient
from .config import load_user_config
from .constants import UNAME_SYSTEM, XDG_BIN_HOME
from .http import request
from .install import (
    configured_package_manager,
    confirm_install,
    find_executable,
    homebrew_install,
    nanobrew_install,
    package_manager_install,
    require_executable,
    wax_install,
)
from .log import error, info, warn

USR_BIN_DIR = Path('/usr/bin')
USR_LOCAL_BIN_DIR = Path('/usr/local/bin')

# TODO: Add more editors
SUPPORTED_EDITORS = {
    'CodeEdit': {
        'cli': 'codeedit',
        'brew': {'formulae': ['codeedit-cli'], 'casks': ['codeedit'], 'taps': ['codeeditapp/formulae']}
    },
    'Cursor': {'cli': 'cursor', 'brew': {'casks': ['cursor']}},
    'Devin Desktop': {'cli': 'devin-desktop', 'brew': {'casks': ['devin-desktop']}},
    'Eclipse Theia': {'cli': '/Applications/TheiaIDE.app/Contents/MacOS/TheiaIDE', 'brew': {'casks': ['theiaide']}},
    'Emacs': {'cli': 'emacs', 'brew': {'formulae': ['emacs']}},
    'Google Antigravity IDE': {'cli': 'agy-ide', 'brew': {'casks': ['antigravity-ide']}},
    'Helix': {'cli': 'hx', 'brew': {'formulae': ['helix']}},
    'Kakoune': {'cli': 'kak', 'brew': {'formulae': ['kakoune']}},
    'Lapce': {'cli': 'lapce', 'brew': {'casks': ['lapce']}},
    'Micro': {'cli': 'micro', 'brew': {'formulae': ['micro']}},
    'Nano': {'cli': 'nano', 'brew': {'formulae': ['nano']}},
    'Neovim': {'cli': 'nvim', 'brew': {'formulae': ['neovim']}},
    'PyCharm': {'cli': 'pycharm', 'brew': {'casks': ['pycharm']}},
    'Sublime Text': {'cli': 'subl', 'brew': {'casks': ['sublime-text']}},
    'TextMate': {'cli': 'mate', 'brew': {'casks': ['textmate']}},
    'Vim': {'cli': 'vim', 'brew': {'formulae': ['vim']}},
    'Visual Studio Code': {'cli': 'code', 'brew': {'casks': ['visual-studio-code']}},
    'VSCodium': {'cli': 'codium', 'brew': {'casks': ['vscodium']}},
    'Zed': {'cli': 'zed', 'brew': {'casks': ['zed']}}
}

def executable_fallbacks(cli: str) -> list[Path]:
    """Return the standard fallback paths for a local executable."""
    cli_path = Path(cli)
    if cli_path.is_absolute():
        return [cli_path]
    return [XDG_BIN_HOME / cli, USR_LOCAL_BIN_DIR / cli, USR_BIN_DIR / cli]

def install_sshfs():
    """Install SSHFS using the configured package manager."""
    package_manager = configured_package_manager()
    if UNAME_SYSTEM == 'Darwin':
        if package_manager == 'homebrew':
            homebrew_install(casks=['fuse-t-sshfs'], taps=['macos-fuse-t/cask'])
        elif package_manager == 'nanobrew':
            nanobrew_install(casks=['macos-fuse-t/cask/fuse-t-sshfs'])
        elif package_manager == 'wax':
            warn('Wax cannot find the fuse-t-sshfs cask for some reason, falling back to Homebrew.')
            homebrew_install(casks=['fuse-t-sshfs'], taps=['macos-fuse-t/cask'])
        elif package_manager == 'zerobrew':
            warn('Zerobrew does not support installing taps or casks yet, falling back to Homebrew.')
            homebrew_install(casks=['fuse-t-sshfs'], taps=['macos-fuse-t/cask'])
        else:
            error('Please install fuse-t-sshfs manually.')
    elif UNAME_SYSTEM == 'Linux':
        package_manager_install(formulae=['sshfs'], packages=['sshfs'])
    elif UNAME_SYSTEM == 'Windows':
        error('Windows is not yet supported.')
    else:
        error('Your OS is not yet supported.')

def mount_remote(mount_point: Path | None = None, mode: str = 'sshfs'):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('Challenge is not running, start a challenge first.')

    user_config = load_user_config()
    package_manager = user_config['package_manager'][UNAME_SYSTEM]

    ssh_config = user_config['ssh']
    project_path = Path(ssh_config['project_path'])
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()

    mount_point = Path(mount_point or ssh_config['mount_point']).expanduser().resolve()
    mount_point.mkdir(0o755, True, True)
    if list(mount_point.iterdir()):
        info('Mount point is non-empty, assuming project path is already mounted')
        return

    if mode == 'mfusepy':
        if UNAME_SYSTEM == 'Darwin':
            if not Path('/Library/Frameworks/fuse_t.framework').is_dir():
                confirm_install('fuse-t', package_manager)
                info('Installing fuse-t...')
                if package_manager == 'homebrew':
                    homebrew_install(casks=['fuse-t'], taps=['macos-fuse-t/cask'])
                elif package_manager == 'nanobrew':
                    nanobrew_install(casks=['macos-fuse-t/cask/fuse-t'])
                elif package_manager == 'wax':
                    wax_install(casks=['fuse-t'], taps=['macos-fuse-t/cask'])
                elif package_manager == 'zerobrew':
                    warn('Zerobrew does not support installing casks yet, falling back to Homebrew')
                    homebrew_install(casks=['fuse-t'], taps=['macos-fuse-t/cask'])
                else:
                    error('Please install fuse-t manually.')
                if not Path('/Library/Frameworks/fuse_t.framework').is_dir():
                    error('fuse-t is still missing after installation.')
        elif UNAME_SYSTEM == 'Linux':
            # libfuse should already be shipped by all major Linux distributions
            error('libfuse should already be shipped by all major Linux distributions. If not, install it manually.')
        elif UNAME_SYSTEM == 'Windows':
            error('Windows is not yet supported.')
        else:
            error('Your OS is not yet supported.')

        # TODO: Figure out how to background this
        info('Keep this process open, press Ctrl+C to unmount the filesystem')
        fuse.FUSE(RemoteClient(), str(mount_point), foreground=True, nothreads=True)
        info('Unmounting the filesystem...')

    elif mode == 'sshfs':
        sshfs = require_executable(
            'sshfs',
            executable_fallbacks('sshfs'),
            display_name='SSHFS',
            installer=install_sshfs,
            method=package_manager,
        )
        if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
            subprocess.run(
                [str(sshfs), '-F', str(ssh_config_file), f'{ssh_config['Host']}:{project_path}', str(mount_point)],
                check=True,
            )
        elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
            subprocess.run([
                str(sshfs), '-p', str(ssh_config['Port']),
                '-o', f'IdentityFile={ssh_identity_file}',
                '-o', f'ServerAliveCountMax={ssh_config['ServerAliveCountMax']}',
                '-o', f'ServerAliveInterval={ssh_config['ServerAliveInterval']}',
                f'{ssh_config['User']}@{ssh_config['HostName']}:{project_path}', str(mount_point)
            ], check=True)
        else:
            error('Something went wrong with the SSH config file or the SSH key, please make sure at least one is valid.')

    info(f'Run [b cyan]dojo umount -p {mount_point}[/] to unmount the filesystem.')

def unmount_remote(mount_point: Path | None = None, mode: str = 'sshfs'):
    mount_point = Path(mount_point or load_user_config()['ssh']['mount_point']).expanduser().resolve()

    if UNAME_SYSTEM == 'Darwin':
        subprocess.run(['diskutil', 'umount', 'force', str(mount_point)], check=True)
    elif UNAME_SYSTEM == 'Linux':
        subprocess.run(['umount', '-f', str(mount_point)], check=True)
    elif UNAME_SYSTEM == 'Windows':
        subprocess.run(['net', 'use', str(mount_point), '/d', '/y'], check=True)
    else:
        error(f'Unsupported platform: {UNAME_SYSTEM}')

def install_editor(editor_name: str, editor: dict) -> Path:
    """Resolve a supported editor, installing it after confirmation if needed."""
    cli = editor['cli']
    package_manager = configured_package_manager()

    def installer():
        if package_manager == 'nanobrew' and 'taps' in editor['brew']:
            error(f'Please install {cli} manually.')
        package_manager_install(
            editor['brew'].get('formulae'),
            editor['brew'].get('casks'),
            editor['brew'].get('taps'),
        )

    return require_executable(
        cli,
        executable_fallbacks(cli),
        display_name=editor_name,
        installer=installer,
        method=package_manager,
    )

def run_editor(editor_name: str, path: Path | None = None, mount_point: Path | None = None):
    cli = str(SUPPORTED_EDITORS[editor_name]['cli']) if editor_name in SUPPORTED_EDITORS else editor_name
    cli_path = find_executable(cli, executable_fallbacks(cli))
    if cli_path is None:
        error(f'Editor {cli} not found.')

    path_to_open = Path(mount_point or load_user_config()['ssh']['mount_point']).expanduser().resolve()

    if path:
        path_to_open /= path

    if editor_name in ['Kakoune', 'Micro', 'Nano'] and path_to_open.is_dir():
        error(f'{editor_name} does not support opening directories.')

    completed = subprocess.run([str(cli_path), str(path_to_open)], check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)

def init_editor(editor_name: str | None = None, path: Path | None = None, mount_point: Path | None = None):
    if not editor_name:
        editor_name = load_user_config()['editor']

    mount_remote(mount_point)

    if editor_name in SUPPORTED_EDITORS:
        install_editor(editor_name, SUPPORTED_EDITORS[editor_name])

    if UNAME_SYSTEM == 'Darwin':
        warn(f'You may see a popup like: [b yellow]{editor_name}.app would like to access files on a network volume.[/]')
        warn('If so, please click [b green]Allow[/].')
        warn('Otherwise, you may need to enable Full Disk Access so that the editor can access the mounted volume.')
        warn('If so, navigate to System Settings > Privacy & Security > Full Disk Access.')
        warn(f'Then turn on Full Disk Access permissions for {editor_name}.')
        warn('Press Enter to dismiss this message.')
        input()

    run_editor(editor_name, path, mount_point)
