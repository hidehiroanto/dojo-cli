"""Handles installing and updating package managers, and uses those managers to install and update packages and tools."""

import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from shutil import which

import niquests

from .config import load_user_config
from .constants import (
    CARGO_HOME,
    UNAME_MACHINE,
    UNAME_SYSTEM,
    XDG_BIN_HOME,
    XDG_DATA_HOME,
)
from .log import error, info, warn

if UNAME_SYSTEM == 'Darwin':
    if UNAME_MACHINE == 'arm64':
        HOMEBREW_PREFIX = Path('/opt/homebrew')
    elif UNAME_MACHINE == 'x86_64':
        HOMEBREW_PREFIX = Path('/usr/local')
elif UNAME_SYSTEM == 'Linux':
    HOMEBREW_PREFIX = Path('/home/linuxbrew/.linuxbrew')

NANOBREW_PREFIX = Path('/opt/nanobrew/prefix')

if Path('/opt/zerobrew').is_dir() or UNAME_SYSTEM == 'Darwin':
    ZEROBREW_ROOT = Path('/opt/zerobrew')
else:
    ZEROBREW_ROOT = XDG_DATA_HOME.expanduser() / 'zerobrew'
ZEROBREW_PREFIX = ZEROBREW_ROOT if UNAME_SYSTEM == 'Darwin' else ZEROBREW_ROOT / 'prefix'

HOMEBREW_INSTALL_URL = 'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh'
NANOBREW_INSTALL_URL = 'https://nanobrew.trilok.ai/install'
RUSTUP_INSTALL_URL = 'https://sh.rustup.rs'
SCOOP_INSTALL_URL = 'https://get.scoop.sh'
UV_INSTALL_URL = 'https://astral.sh/uv/install.sh'
ZEROBREW_GITHUB_URL = 'https://github.com/lucasgelfond/zerobrew'
ZEROBREW_INSTALL_URL = 'https://zerobrew.rs/install'

def find_executable(name: str, fallbacks: Iterable[str | Path] = ()) -> Path | None:
    """Find an executable on PATH or at one of the supplied fallback paths."""
    executable = which(name)
    if executable:
        return Path(executable)

    for fallback in fallbacks:
        path = Path(fallback).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path

    return None

def confirm_install(name: str, method: str | None = None):
    """Ask for confirmation before installing a missing program."""
    warn(f'{name} is missing.')
    if not sys.stdin.isatty():
        error(f'Cannot prompt to install {name} because standard input is not interactive.')

    suffix = f' using {method}' if method else ''
    try:
        approved = input(f'Install {name}{suffix}? (y/N) > ').strip()[:1].lower() == 'y'
    except EOFError:
        approved = False

    if not approved:
        error(f'{name} is required.')

def run_install_script(name: str, url: str, interpreter: str | Path | list[str | Path] = 'bash'):
    """Download and execute an official installation script."""
    try:
        response = niquests.get(url)
    except niquests.RequestException as exc:
        error(f'Could not download the {name} installer from {url}: {exc}')
    if not response.ok or not response.text:
        error(f'Could not download the {name} installer from {url}.')

    command = [str(part) for part in interpreter] if isinstance(interpreter, list) else [str(interpreter)]
    completed = subprocess.run(command, input=response.text, text=True, check=False)
    if completed.returncode:
        error(f'The {name} installer exited with code {completed.returncode}.')

def run_optional_update(name: str, command: list[str]):
    """Run a best-effort update and warn if it fails."""
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        warn(f'{name} update exited with code {completed.returncode}; continuing with the installed version.')

def require_executable(
    name: str,
    fallbacks: Iterable[str | Path] = (),
    *,
    display_name: str | None = None,
    installer: Callable[[], None] | None = None,
    method: str | None = None
) -> Path:
    """Resolve an executable, optionally installing it after confirmation."""
    executable = find_executable(name, fallbacks)
    if executable:
        return executable

    display_name = display_name or name
    if installer is None:
        error(f'{display_name} is not installed.')

    confirm_install(display_name, method)
    installer()

    executable = find_executable(name, fallbacks)
    if executable is None:
        error(f'{display_name} is still missing after installation.')
    return executable

def configured_package_manager() -> str:
    """Return the package manager configured for the current operating system."""
    return load_user_config()['package_manager'][UNAME_SYSTEM]

def homebrew_install(
    formulae: list[str] | None = None,
    casks: list[str] | None = None,
    taps: list[str] | None = None,
    skip_update: bool = False
):
    """Install Homebrew formulae and casks."""

    brew_fallback = HOMEBREW_PREFIX / 'bin' / 'brew'
    brew = find_executable('brew', [brew_fallback])
    if brew is None:
        confirm_install('Homebrew', 'the official installer')
        info('Installing Homebrew...')
        run_install_script('Homebrew', HOMEBREW_INSTALL_URL)
        brew = find_executable('brew', [brew_fallback])
        if brew is None:
            error('Homebrew is still missing after installation.')
    elif not skip_update:
        run_optional_update('Homebrew', [str(brew), 'update'])

    if taps:
        for tap in taps:
            subprocess.run([str(brew), 'tap', tap], check=True)
    if casks:
        subprocess.run([str(brew), 'install', '--cask', *casks], check=True)
    if formulae:
        subprocess.run([str(brew), 'install', *formulae], check=True)

def nanobrew_install(
    formulae: list[str] | None = None,
    casks: list[str] | None = None,
    taps: list[str] | None = None,
    skip_update: bool = False
):
    """
    Install formulae and casks using Nanobrew.

    Faster than zerobrew. Faster than homebrew. Written in Zig.
    SIMD extraction + mmap + arena allocators + platform COW copy.
    Works on macOS and Linux.
    """

    nb_fallback = NANOBREW_PREFIX / 'bin' / 'nb'
    nb = find_executable('nb', [nb_fallback])
    if nb is None:
        confirm_install('Nanobrew', 'the official installer')
        info('Installing Nanobrew...')
        run_install_script('Nanobrew', NANOBREW_INSTALL_URL)
        nb = find_executable('nb', [nb_fallback])
        if nb is None:
            error('Nanobrew is still missing after installation.')
    elif not skip_update:
        run_optional_update('Nanobrew', [str(nb), 'update'])

    if taps:
        error('No need to install taps, just install third-party tap formulae e.g. `user/tap/formula` directly')
    if casks:
        subprocess.run([str(nb), 'install', '--cask', *casks], check=True)
    if formulae:
        subprocess.run([str(nb), 'install', *formulae], check=True)

def scoop_install(
    packages: list[str] | None = None,
    buckets: list[str] | None = None,
    skip_update: bool = False
):
    # Requires PowerShell
    # Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
    # Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
    # scoop bucket add main
    # scoop bucket add extras
    # scoop install extras/zed
    # scoop install main/ruff
    # scoop install main/ty

    # TODO: Check if this is legit
    scoop = find_executable('scoop')
    if scoop is None:
        confirm_install('Scoop', 'the official installer')
        info('Installing scoop...')
        powershell = find_executable('powershell') or find_executable('pwsh')
        if powershell is None:
            error('PowerShell is required to install Scoop.')
        subprocess.run(
            [str(powershell), '-NoProfile', '-Command', 'Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser'],
            check=True,
        )
        run_install_script('Scoop', SCOOP_INSTALL_URL, [str(powershell), '-NoProfile', '-Command', '-'])
        scoop = find_executable('scoop')
        if scoop is None:
            error('Scoop is still missing after installation.')
    elif not skip_update:
        # TODO: Update scoop
        pass

    if buckets:
        for bucket in buckets:
            subprocess.run([str(scoop), 'bucket', 'add', bucket], check=True)
    if packages:
        for package in packages:
            subprocess.run([str(scoop), 'install', package], check=True)

def uv_install(
    global_packages: list[str] | None = None,
    local_packages: list[str] | None = None,
    tools: list[str] | None = None,
    skip_update: bool = False
):
    """
    Install Python packages and tools using uv, an extremely fast Python package manager written in Rust.
    This assumes that uv is installed independently and not with another package manager.
    """

    uv_fallback = XDG_BIN_HOME / 'uv'
    uv = find_executable('uv', [uv_fallback])
    if uv is None:
        confirm_install('uv', 'the official installer')
        info('Installing uv...')
        run_install_script('uv', UV_INSTALL_URL)
        uv = find_executable('uv', [uv_fallback])
        if uv is None:
            error('uv is still missing after installation.')
    elif not skip_update:
        run_optional_update('uv', [str(uv), 'self', 'update'])

    if global_packages:
        subprocess.run([str(uv), 'pip', 'install', '-U', '--break-system-packages', '--strict', '--system', *global_packages], check=True)
    if local_packages:
        subprocess.run([str(uv), 'add', '-U', *local_packages], check=True)
    if tools:
        for tool in tools:
            subprocess.run([str(uv), 'tool', 'install', '-U', tool], check=True)

# Use at your own risk, wax can't detect installed casks or Homebrew-added taps
# Installing wax casks may lead to `IO error: Permission denied (os error 13)`
# Using wax to uninstall and reinstall ruff or ty may lead to `IO error: File exists (os error 17)`
def wax_install(
    formulae: list[str] | None = None,
    casks: list[str] | None = None,
    taps: list[str] | None = None,
    skip_update: bool = False
):
    """
    Install formulae and casks using Wax, a fast, modern Homebrew-compatible package manager built in Rust.

    Wax leverages Homebrew's ecosystem without the overhead and provides 16-20x faster search operations
    and parallel installation workflows while maintaining full compatibility with Homebrew formulae and bottles.
    """

    cargo_fallback = CARGO_HOME / 'bin' / 'cargo'
    cargo = find_executable('cargo', [cargo_fallback])
    if cargo is None:
        confirm_install('Rust', 'Rustup')
        info('Installing Rust...')
        run_install_script('Rust', RUSTUP_INSTALL_URL)
        cargo = find_executable('cargo', [cargo_fallback])
        if cargo is None:
            error('Cargo is still missing after installing Rust.')

    wax_fallback = CARGO_HOME / 'bin' / 'wax'
    wax = find_executable('wax', [wax_fallback])
    if wax is None:
        confirm_install('Wax', 'Cargo')
        info('Installing Wax...')
        subprocess.run([str(cargo), 'install', 'waxpkg'], check=True)
        wax = find_executable('wax', [wax_fallback])
        if wax is None:
            error('Wax is still missing after installation.')
    elif not skip_update:
        run_optional_update('Wax', [str(wax), 'update', '-s'])

    if taps:
        for tap in taps:
            subprocess.run([str(wax), 'tap', 'add', tap], check=True)
    if casks:
        subprocess.run([str(wax), 'c', *casks], check=True)
    if formulae:
        subprocess.run([str(wax), 'i', *formulae], check=True)

def zerobrew_install(
    formulae: list[str] | None = None,
    casks: list[str] | None = None,
    taps: list[str] | None = None,
    skip_update: bool = False
):
    """
    Install Homebrew formulae and casks using the Zerobrew package manager.

    Zerobrew is a drop-in, 5-20x faster, experimental Homebrew alternative written in Rust.
    Zerobrew brings uv-style architecture to Homebrew packages on macOS and Linux.
    """

    zb_fallback = XDG_BIN_HOME / 'zb'
    zb = find_executable('zb', [zb_fallback])
    if zb is None:
        confirm_install('Zerobrew', 'the official installer')
        info('Installing Zerobrew...')
        run_install_script('Zerobrew', ZEROBREW_INSTALL_URL)
        zb = find_executable('zb', [zb_fallback])
        if zb is None:
            error('Zerobrew is still missing after installation.')
    elif not skip_update:
        info('Updating Zerobrew...')
        run_install_script('Zerobrew', ZEROBREW_INSTALL_URL)

    if taps:
        # TODO: replace this when zerobrew supports taps
        error('Zerobrew does not support taps other than homebrew/core yet.')
    if casks:
        # Fall back to homebrew for now
        # TODO: replace this when zerobrew supports casks
        warn('Zerobrew does not support installing casks yet, falling back to Homebrew...')
        homebrew_install(casks=casks)
    if formulae:
        subprocess.run([str(zb), 'install', *formulae], check=True)

def package_manager_install(
    formulae: list[str] | None = None,
    casks: list[str] | None = None,
    taps: list[str] | None = None,
    packages: list[str] | None = None,
    skip_update: bool = False
):
    """Install packages using the configured package manager."""
    package_manager = configured_package_manager()
    if package_manager == 'homebrew':
        homebrew_install(formulae, casks, taps, skip_update)
    elif package_manager == 'nanobrew':
        nanobrew_install(formulae, casks, taps, skip_update)
    elif package_manager == 'wax':
        wax_install(formulae, casks, taps, skip_update)
    elif package_manager == 'zerobrew':
        zerobrew_install(formulae, casks, taps, skip_update)
    elif package_manager == 'scoop':
        scoop_install(packages or formulae or casks, skip_update=skip_update)
    else:
        error(f'Unsupported package manager: {package_manager}')

# TODO: add support for other package managers
