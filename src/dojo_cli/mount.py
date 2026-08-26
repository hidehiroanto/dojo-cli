"""Mount remote project paths through SSHFS or mfusepy."""

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Literal, cast

from .config import load_user_config
from .constants import UNAME_SYSTEM, XDG_BIN_HOME
from .http import request
from .install import confirm_install, find_executable, homebrew_install, nanobrew_install, package_manager_install, wax_install
from .log import error, info, warn

type MountImplementation = Literal['sshfs', 'mfusepy']
type FuseProvider = Literal['auto', 'fuse-t', 'macfuse']

IMPLEMENTATIONS = {'sshfs', 'mfusepy'}
PROVIDERS = {'auto', 'fuse-t', 'macfuse'}
FUSE_LIBRARIES = {'fuse-t': Path('/usr/local/lib/libfuse-t.dylib'), 'macfuse': Path('/usr/local/lib/libfuse.dylib')}
SSHFS_RECEIPTS = {'fuse-t': 'org.sshfs.', 'macfuse': 'io.macfuse.installer.components.sshfs'}
SSHFS_FALLBACKS = [XDG_BIN_HOME / 'sshfs', Path('/usr/local/bin/sshfs'), Path('/usr/bin/sshfs')]


def package_receipts() -> set[str]:
    """Return package receipts installed on macOS."""
    try:
        result = subprocess.run(['pkgutil', '--pkgs'], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        error(f'Could not inspect installed macOS packages: {exc}')
    return set(result.stdout.splitlines())


def installed_sshfs_providers(receipts: set[str] | None = None) -> set[str]:
    """Return providers with installed SSHFS package receipts."""
    receipts = package_receipts() if receipts is None else receipts
    return {provider for provider, prefix in SSHFS_RECEIPTS.items() if any(receipt.startswith(prefix) for receipt in receipts)}


def installed_runtime_providers() -> set[str]:
    """Return providers with an available libfuse compatibility library."""
    return {provider for provider, library in FUSE_LIBRARIES.items() if library.is_file()}


def resolve_mount_options(implementation: str | None, provider: str | None) -> tuple[MountImplementation, FuseProvider]:
    """Resolve and validate command overrides and configured mount defaults."""
    mount_config = load_user_config()['mount']
    implementation = implementation or mount_config['implementation']
    provider = provider or mount_config['provider']
    if implementation not in IMPLEMENTATIONS:
        error(f'Unsupported mount implementation: {implementation}')
    if provider not in PROVIDERS:
        error(f'Unsupported FUSE provider: {provider}')
    return cast(MountImplementation, implementation), cast(FuseProvider, provider)


def resolve_provider(requested: FuseProvider, implementation: MountImplementation) -> str:
    """Resolve automatic provider selection and reject ambiguous installations."""
    if UNAME_SYSTEM != 'Darwin':
        if requested != 'auto':
            error('FUSE providers can only be selected on macOS.')
        return 'auto'

    if implementation == 'sshfs':
        installed = installed_sshfs_providers()
        if len(installed) > 1:
            error(
                'Both fuse-t-sshfs and sshfs-mac are installed and claim /usr/local/bin/sshfs. Uninstall one before mounting.'
            )
        if requested != 'auto' and installed and requested not in installed:
            installed_provider = next(iter(installed))
            error(f'The installed SSHFS client belongs to {installed_provider}, not {requested}.')
        return requested if requested != 'auto' else next(iter(installed), 'fuse-t')

    if requested != 'auto':
        return requested
    installed = installed_runtime_providers()
    if 'fuse-t' in installed:
        return 'fuse-t'
    if 'macfuse' in installed:
        return 'macfuse'
    return 'fuse-t'


def install_fuse_provider(provider: str, include_sshfs: bool, package_manager: str):
    """Install one matched macOS FUSE runtime or SSHFS stack."""
    display_name = {
        ('fuse-t', False): 'FUSE-T',
        ('fuse-t', True): 'FUSE-T and SSHFS',
        ('macfuse', False): 'macFUSE',
        ('macfuse', True): 'macFUSE and SSHFS',
    }[provider, include_sshfs]
    confirm_install(display_name, package_manager)
    info(f'Installing {display_name}...')

    cask = 'fuse-t-sshfs' if provider == 'fuse-t' and include_sshfs else provider
    if provider == 'macfuse' and include_sshfs:
        cask = 'sshfs-mac'

    if package_manager == 'homebrew':
        taps = ['macos-fuse-t/cask'] if provider == 'fuse-t' and include_sshfs else None
        homebrew_install(casks=[cask], taps=taps)
    elif package_manager == 'nanobrew':
        if provider == 'fuse-t' and include_sshfs:
            cask = 'macos-fuse-t/cask/fuse-t-sshfs'
        nanobrew_install(casks=[cask])
    elif package_manager == 'wax':
        if include_sshfs:
            warn(f'Wax cannot reliably install {display_name}, falling back to Homebrew.')
            taps = ['macos-fuse-t/cask'] if provider == 'fuse-t' else None
            homebrew_install(casks=[cask], taps=taps)
        else:
            wax_install(casks=[cask])
    elif package_manager == 'zerobrew':
        warn(f'Zerobrew cannot install {display_name}, falling back to Homebrew.')
        taps = ['macos-fuse-t/cask'] if provider == 'fuse-t' and include_sshfs else None
        homebrew_install(casks=[cask], taps=taps)
    else:
        error(f'Please install {display_name} manually.')


def ensure_mfusepy_provider(provider: str, package_manager: str):
    """Ensure the selected provider library is available for mfusepy."""
    library = FUSE_LIBRARIES[provider]
    if not library.is_file():
        install_fuse_provider(provider, False, package_manager)
    if not library.is_file():
        error(f'{provider} is still missing after installation.')


def ensure_sshfs_provider(provider: str, package_manager: str) -> Path:
    """Ensure one unambiguous matched SSHFS stack is installed."""
    installed = installed_sshfs_providers()
    if len(installed) > 1:
        error('Both fuse-t-sshfs and sshfs-mac are installed and claim /usr/local/bin/sshfs. Uninstall one before mounting.')
    if installed and provider not in installed:
        installed_provider = next(iter(installed))
        error(f'The installed SSHFS client belongs to {installed_provider}, not {provider}.')
    if not installed:
        install_fuse_provider(provider, True, package_manager)
        installed = installed_sshfs_providers()
    if installed != {provider}:
        error(f'The {provider} SSHFS stack is still missing after installation.')
    if not FUSE_LIBRARIES[provider].is_file():
        error(f'The {provider} SSHFS runtime is missing.')
    executable = find_executable('sshfs', SSHFS_FALLBACKS)
    if executable is None:
        error('SSHFS is still missing after installation.')
    return executable


def load_mfusepy(provider: str) -> ModuleType:
    """Load mfusepy with the selected provider library."""
    library = FUSE_LIBRARIES[provider].resolve()
    loaded = sys.modules.get('mfusepy')
    if loaded is not None:
        loaded_library = Path(loaded._libfuse._name).resolve()
        if loaded_library != library:
            error(f'mfusepy is already using {loaded_library}, not {library}.')
        return loaded
    os.environ['FUSE_LIBRARY_PATH'] = str(library)
    import mfusepy

    loaded_library = Path(mfusepy._libfuse._name).resolve()
    if loaded_library != library:
        error(f'mfusepy loaded {loaded_library}, not {library}.')
    return mfusepy


def mount_remote(mount_point: Path | None = None, implementation: str | None = None, provider: str | None = None):
    """Mount the configured remote project path locally."""
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('Challenge is not running, start a challenge first.')

    implementation, requested_provider = resolve_mount_options(implementation, provider)
    selected_provider = resolve_provider(requested_provider, implementation)
    user_config = load_user_config()
    package_manager = user_config['package_manager'][UNAME_SYSTEM]
    ssh_config = user_config['ssh']
    project_path = Path(ssh_config['project_path'])
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()

    mount_point = Path(mount_point or ssh_config['mount_point']).expanduser().resolve()
    mount_point.mkdir(0o755, True, True)
    if mount_point.is_mount():
        info('Project path is already mounted.')
        return
    if any(mount_point.iterdir()):
        error(f'Mount point {mount_point} is non-empty but is not a mount.')

    if implementation == 'mfusepy':
        if UNAME_SYSTEM != 'Darwin':
            error('mfusepy mounts are only supported on macOS.')
        ensure_mfusepy_provider(selected_provider, package_manager)
        fuse = load_mfusepy(selected_provider)
        from .client import RemoteClient

        info(f'Mounting with mfusepy and {selected_provider}. Press Ctrl+C to unmount.')
        fuse.FUSE(RemoteClient(), str(mount_point), foreground=True, nothreads=True)
        info('Unmounting the filesystem...')
    elif UNAME_SYSTEM == 'Darwin':
        sshfs = ensure_sshfs_provider(selected_provider, package_manager)
        mount_sshfs(sshfs, mount_point, project_path, ssh_config, ssh_config_file, ssh_identity_file)
    elif UNAME_SYSTEM == 'Linux':
        sshfs = find_executable('sshfs', SSHFS_FALLBACKS)
        if sshfs is None:
            confirm_install('SSHFS', package_manager)
            package_manager_install(formulae=['sshfs'], packages=['sshfs'])
            sshfs = find_executable('sshfs', SSHFS_FALLBACKS)
        if sshfs is None:
            error('SSHFS is still missing after installation.')
        mount_sshfs(sshfs, mount_point, project_path, ssh_config, ssh_config_file, ssh_identity_file)
    elif UNAME_SYSTEM == 'Windows':
        error('Windows is not yet supported.')
    else:
        error(f'Unsupported platform: {UNAME_SYSTEM}')

    info(f'Run [b cyan]dojo umount -p {mount_point}[/] to unmount the filesystem.')


def mount_sshfs(
    sshfs: Path, mount_point: Path, project_path: Path, ssh_config: dict, ssh_config_file: Path, ssh_identity_file: Path
):
    """Run SSHFS using the configured SSH host or identity."""
    if ssh_config_file.is_file() and f'Host {ssh_config["Host"]}' in ssh_config_file.read_text():
        subprocess.run(
            [str(sshfs), '-F', str(ssh_config_file), f'{ssh_config["Host"]}:{project_path}', str(mount_point)], check=True
        )
    elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
        subprocess.run(
            [
                str(sshfs),
                '-p',
                str(ssh_config['Port']),
                '-o',
                f'IdentityFile={ssh_identity_file}',
                '-o',
                f'ServerAliveCountMax={ssh_config["ServerAliveCountMax"]}',
                '-o',
                f'ServerAliveInterval={ssh_config["ServerAliveInterval"]}',
                f'{ssh_config["User"]}@{ssh_config["HostName"]}:{project_path}',
                str(mount_point),
            ],
            check=True,
        )
    else:
        error('Something went wrong with the SSH config file or the SSH key. Please make sure at least one is valid.')


def unmount_remote(mount_point: Path | None = None, force: bool = False):
    """Unmount a local remote-project mount point."""
    mount_point = Path(mount_point or load_user_config()['ssh']['mount_point']).expanduser().resolve()
    if UNAME_SYSTEM == 'Darwin':
        command = ['diskutil', 'unmount']
        if force:
            command.append('force')
        subprocess.run([*command, str(mount_point)], check=True)
    elif UNAME_SYSTEM == 'Linux':
        subprocess.run(['umount', *(['-f'] if force else []), str(mount_point)], check=True)
    elif UNAME_SYSTEM == 'Windows':
        subprocess.run(['net', 'use', str(mount_point), '/d', '/y'], check=True)
    else:
        error(f'Unsupported platform: {UNAME_SYSTEM}')
