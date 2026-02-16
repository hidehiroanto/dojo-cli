"""
Handles installing, updating, and launching SSHFS and code editors.
"""

# TODO: Add more package managers, Windows support?
# TODO: Move mount stuff to mount.py?

import mfusepy as fuse
import os
from pathlib import Path
from shutil import which
import subprocess
import sys
from typing import Optional

from .client import RemoteClient
from .config import load_user_config
from .http import request
from .install import homebrew_install, wax_install, zerobrew_install
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
    'Emacs': {'cli': 'emacs', 'brew': {'formulae': ['emacs']}},
    'Google Antigravity': {'cli': 'agy', 'brew': {'casks': ['antigravity']}},
    'Helix': {'cli': 'hx', 'brew': {'formulae': ['helix']}},
    'Kakoune': {'cli': 'kak', 'brew': {'formulae': ['kakoune']}},
    'Lapce': {'cli': 'lapce', 'brew': {'casks': ['lapce']}},
    'Micro': {'cli': 'micro', 'brew': {'formulae': ['micro']}},
    'Nano': {'cli': 'nano', 'brew': {'formulae': ['nano']}},
    'Neovim': {'cli': 'nvim', 'brew': {'formulae': ['neovim']}},
    'PyCharm': {'cli': 'pycharm', 'brew': {'casks': ['pycharm']}},
    'Sublime Text': {'cli': 'subl', 'brew': {'casks': ['sublime-text']}},
    'Vim': {'cli': 'vim', 'brew': {'formulae': ['vim']}},
    'Visual Studio Code': {'cli': 'code', 'brew': {'casks': ['visual-studio-code']}},
    'VSCodium': {'cli': 'codium', 'brew': {'casks': ['vscodium']}},
    'Windsurf': {'cli': 'windsurf', 'brew': {'casks': ['windsurf']}},
    'Zed': {'cli': 'zed', 'brew': {'casks': ['zed']}}
}

def mount_remote(mount_point: Optional[Path] = None, mode: str = 'sshfs'):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('Challenge is not running, start a challenge first.')

    user_config = load_user_config()
    package_manager = user_config['package_manager'][sys.platform]

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
        if sys.platform == 'darwin':
            # maybe use macfuse instead when macfuse 5.2 comes out without kext
            info('Installing fuse-t...')
            if package_manager == 'homebrew':
                homebrew_install(casks=['fuse-t'], taps=['macos-fuse-t/cask'])
            elif package_manager == 'wax':
                wax_install(casks=['fuse-t'], taps=['macos-fuse-t/cask'])
            elif package_manager == 'zerobrew':
                warn('Zerobrew does not support installing casks yet, falling back to Homebrew')
                homebrew_install(casks=['fuse-t'], taps=['macos-fuse-t/cask'])
            else:
                # TODO: Implement "manual" fuse-t installation
                error('Please install fuse-t manually.')
        elif sys.platform == 'linux':
            # libfuse should already be shipped by all major Linux distributions
            error('libfuse should already be shipped by all major Linux distributions. If not, install it manually.')
        elif sys.platform == 'win32':
            error('Windows is not yet supported.')
        else:
            error('Your OS is not yet supported.')

        # TODO: Figure out how to background this
        info('Keep this process open, press Ctrl+C to unmount the filesystem')
        fuse.FUSE(RemoteClient(), str(mount_point), foreground=True, nothreads=True)
        info('Unmounting the filesystem...')

    elif mode == 'sshfs':
        sshfs = Path(which('sshfs') or USR_LOCAL_BIN_DIR / 'sshfs')
        if not sshfs.is_file():
            if sys.platform == 'darwin':
                # maybe use macfuse + sshfs when macfuse 5.2 comes out without kext
                info('Installing fuse-t-sshfs...')
                if package_manager == 'homebrew':
                    homebrew_install(casks=['fuse-t-sshfs'], taps=['macos-fuse-t/cask'])
                elif package_manager == 'wax':
                    warn('Wax cannot find the fuse-t-sshfs cask for some reason, falling back to Homebrew.')
                    homebrew_install(casks=['fuse-t-sshfs'], taps=['macos-fuse-t/cask'])
                elif package_manager == 'zerobrew':
                    warn('Zerobrew does not support installing taps or casks yet, falling back to Homebrew.')
                    homebrew_install(casks=['fuse-t-sshfs'], taps=['macos-fuse-t/cask'])
                else:
                    # TODO: Implement "manual" fuse-t-sshfs installation
                    error('Please install fuse-t-sshfs manually.')
            elif sys.platform == 'linux':
                # sshfs should already be shipped by all major Linux distributions
                if package_manager == 'homebrew':
                    homebrew_install(['sshfs'])
                elif package_manager == 'wax':
                    wax_install(['sshfs'])
                elif package_manager == 'zerobrew':
                    zerobrew_install(['sshfs'])
                else:
                    # TODO: Implement "manual" sshfs installation
                    error('Please install sshfs manually.')
            elif sys.platform == 'win32':
                error('Windows is not yet supported.')
            else:
                error('Your OS is not yet supported.')

        if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
            subprocess.run([sshfs, '-F', ssh_config_file, f'{ssh_config['Host']}:{project_path}', mount_point])
        elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
            subprocess.run([
                sshfs, '-p', str(ssh_config['Port']),
                '-o', f'IdentityFile={ssh_identity_file}',
                '-o', f'ServerAliveCountMax={ssh_config['ServerAliveCountMax']}',
                '-o', f'ServerAliveInterval={ssh_config['ServerAliveInterval']}',
                f'{ssh_config['User']}@{ssh_config['HostName']}:{project_path}', mount_point
            ])
        else:
            error('Something went wrong with the SSH config file or the SSH key, please make sure at least one is valid.')

    if sys.platform == 'darwin':
        info(f'To unmount, run: [bold cyan]diskutil umount {mount_point}[/]')
        info(f'If that does not work, run: [bold cyan]diskutil umount force {mount_point}[/]')
    elif sys.platform == 'linux':
        info(f'To unmount, run: [bold cyan]umount {mount_point}[/]')
        info(f'If that does not work, run: [bold cyan]umount -f {mount_point}[/]')
    elif sys.platform == 'win32':
        info(f'To unmount, run: [bold cyan]net use {mount_point} /d[/]')
        info(f'If that does not work, run: [bold cyan]net use {mount_point} /d /y[/]')
    else:
        error(f'Unsupported platform: {sys.platform}')

def install_editor(editor):
    if which(editor['cli']) or (USR_LOCAL_BIN_DIR / editor['cli']).is_file() or (USR_BIN_DIR / editor['cli']).is_file():
        info(f'{editor['cli']} is already installed.')
        return

    package_manager = load_user_config()['package_manager'][sys.platform]
    if package_manager == 'homebrew':
        homebrew_install(editor['brew'].get('formulae'), editor['brew'].get('casks'), editor['brew'].get('taps'))
    elif package_manager == 'wax':
        # Avoid using, wax cask installation is broken, IO error: Permission denied (os error 13)
        wax_install(editor['brew'].get('formulae'), editor['brew'].get('casks'), editor['brew'].get('taps'))
    elif package_manager == 'zerobrew':
        zerobrew_install(editor['brew'].get('formulae'), editor['brew'].get('casks'), editor['brew'].get('taps'))
    else:
        # TODO: Implement "manual" editor installation
        error(f'Please install {editor['cli']} manually.')

def run_editor(editor_name: str, mount_point: Optional[Path] = None, path: Optional[Path] = None):
    cli = str(SUPPORTED_EDITORS[editor_name]['cli']) if editor_name in SUPPORTED_EDITORS else editor_name
    which_cli = which(cli)

    if which_cli:
        cli_path = Path(which_cli)
    elif (USR_LOCAL_BIN_DIR / cli).is_file():
        cli_path = USR_LOCAL_BIN_DIR / cli
    elif (USR_BIN_DIR / cli).is_file():
        cli_path = USR_BIN_DIR / cli
    else:
        error(f'Editor {cli} not found.')
        return

    path_to_open = Path(mount_point or load_user_config()['ssh']['mount_point']).expanduser().resolve()

    if path:
        path_to_open /= path

    if editor_name in ['Kakoune', 'Micro', 'Nano'] and path_to_open.is_dir():
        error(f'{editor_name} does not support opening directories.')

    subprocess.run([cli_path, path_to_open])

def init_editor(editor_name: Optional[str] = None, mount_point: Optional[Path] = None, path: Optional[Path] = None):
    if not editor_name:
        editor_name = load_user_config()['code_editor']

    mount_remote(mount_point)

    if editor_name in SUPPORTED_EDITORS:
        install_editor(SUPPORTED_EDITORS[editor_name])

    if sys.platform == 'darwin':
        warn(f'You may see a popup like: [bold yellow]{editor_name}.app would like to access files on a network volume.[/]')
        warn('If so, please click [bold green]Allow[/].')
        warn('Otherwise, you may need to enable Full Disk Access so that the editor can access the mounted volume.')
        warn('If so, navigate to System Settings > Privacy & Security > Full Disk Access.')
        warn(f'Then turn on Full Disk Access permissions for {editor_name}.')
        warn('Press Enter to dismiss this message.')
        input()

    run_editor(editor_name, mount_point, path)
