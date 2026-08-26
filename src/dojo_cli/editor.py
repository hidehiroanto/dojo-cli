"""Handles installing, updating, and launching code editors."""

# TODO: Add more package managers, Windows support?

import subprocess
from pathlib import Path

from .config import load_user_config
from .constants import UNAME_SYSTEM, XDG_BIN_HOME
from .install import configured_package_manager, find_executable, package_manager_install, require_executable
from .log import error, warn

USR_BIN_DIR = Path('/usr/bin')
USR_LOCAL_BIN_DIR = Path('/usr/local/bin')

# TODO: Add more editors
SUPPORTED_EDITORS = {
    'CodeEdit': {
        'cli': 'codeedit',
        'brew': {'formulae': ['codeedit-cli'], 'casks': ['codeedit'], 'taps': ['codeeditapp/formulae']},
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
    'Zed': {'cli': 'zed', 'brew': {'casks': ['zed']}},
}


def executable_fallbacks(cli: str) -> list[Path]:
    """Return the standard fallback paths for a local executable."""
    cli_path = Path(cli)
    if cli_path.is_absolute():
        return [cli_path]
    return [XDG_BIN_HOME / cli, USR_LOCAL_BIN_DIR / cli, USR_BIN_DIR / cli]


def install_editor(editor_name: str, editor: dict) -> Path:
    """Resolve a supported editor, installing it after confirmation if needed."""
    cli = editor['cli']
    package_manager = configured_package_manager()

    def installer():
        if package_manager == 'nanobrew' and 'taps' in editor['brew']:
            error(f'Please install {cli} manually.')
        package_manager_install(editor['brew'].get('formulae'), editor['brew'].get('casks'), editor['brew'].get('taps'))

    return require_executable(
        cli, executable_fallbacks(cli), display_name=editor_name, installer=installer, method=package_manager
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


def init_editor(
    editor_name: str | None = None,
    path: Path | None = None,
    mount_point: Path | None = None,
    implementation: str | None = None,
    provider: str | None = None,
):
    if not editor_name:
        editor_name = load_user_config()['editor']

    from .mount import mount_remote

    mount_remote(mount_point, implementation, provider)

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
