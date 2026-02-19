"""
Handles installing and updating package managers, and uses those managers to install and update packages and tools.
"""

from pathlib import Path
import requests
from shutil import which
import subprocess
from typing import Optional

from .constants import CARGO_HOME, UNAME_MACHINE, UNAME_SYSTEM, XDG_BIN_HOME, XDG_DATA_HOME
from .log import error, info, warn

if UNAME_SYSTEM == 'Darwin':
    if UNAME_MACHINE == 'arm64':
        HOMEBREW_PREFIX = Path('/opt/homebrew')
    elif UNAME_MACHINE == 'x86_64':
        HOMEBREW_PREFIX = Path('/usr/local')
elif UNAME_SYSTEM == 'Linux':
    HOMEBREW_PREFIX = Path('/home/linuxbrew/.linuxbrew')

if Path('/opt/zerobrew').is_dir() or UNAME_SYSTEM == 'Darwin':
    ZEROBREW_ROOT = Path('/opt/zerobrew')
else:
    ZEROBREW_ROOT = XDG_DATA_HOME / 'zerobrew'
ZEROBREW_PREFIX = ZEROBREW_ROOT if UNAME_SYSTEM == 'Darwin' else ZEROBREW_ROOT / 'prefix'

HOMEBREW_INSTALL_URL = 'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh'
RUSTUP_INSTALL_URL = 'https://sh.rustup.rs'
SCOOP_INSTALL_URL = 'https://get.scoop.sh'
UV_INSTALL_URL = 'https://astral.sh/uv/install.sh'
ZEROBREW_GITHUB_URL = 'https://github.com/lucasgelfond/zerobrew'
ZEROBREW_INSTALL_URL = 'https://zerobrew.rs/install'

def homebrew_install(
    formulae: Optional[list[str]] = None,
    casks: Optional[list[str]] = None,
    taps: Optional[list[str]] = None,
    skip_update: bool = False
):
    """Install Homebrew formulae and casks."""

    brew = Path(which('brew') or HOMEBREW_PREFIX / 'bin' / 'brew')
    if not brew.is_file():
        info('Installing Homebrew...')
        subprocess.run(['bash', '-c', requests.get(HOMEBREW_INSTALL_URL).text])
    elif not skip_update:
        subprocess.run([brew, 'update'])

    if taps:
        for tap in taps:
            subprocess.run([brew, 'tap', tap])
    if casks:
        subprocess.run([brew, 'install', '--cask'] + casks)
    if formulae:
        subprocess.run([brew, 'install'] + formulae)

def scoop_install(
    packages: Optional[list[str]] = None,
    buckets: Optional[list[str]] = None,
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
    scoop = Path(which('scoop') or 'scoop')
    if not scoop.is_file():
        info('Installing scoop...')
        subprocess.run(['Set-ExecutionPolicy', '-ExecutionPolicy', 'RemoteSigned', '-Scope', 'CurrentUser'])
        subprocess.run(requests.get(SCOOP_INSTALL_URL).text, shell=True)
    elif not skip_update:
        # TODO: Update scoop
        pass

    if buckets:
        for bucket in buckets:
            subprocess.run(['scoop', 'bucket', 'add', bucket])
    if packages:
        for package in packages:
            subprocess.run(['scoop', 'install', package])

def uv_install(
    global_packages: Optional[list[str]] = None,
    local_packages: Optional[list[str]] = None,
    tools: Optional[list[str]] = None,
    skip_update: bool = False
):
    """
    Install Python packages and tools using uv, an extremely fast Python package manager written in Rust.
    This assumes that uv is installed independently and not with another package manager.
    """

    uv = Path(which('uv') or XDG_BIN_HOME / 'uv')
    if not uv.is_file():
        info('Installing uv...')
        subprocess.run(requests.get(UV_INSTALL_URL).text, shell=True)
    elif not skip_update:
        subprocess.run([uv, 'self', 'update'])

    if global_packages:
        subprocess.run([uv, 'pip', 'install', '-U', '--break-system-packages', '--strict', '--system'] + global_packages)
    if local_packages:
        subprocess.run([uv, 'add', '-U'] + local_packages)
    if tools:
        for tool in tools:
            subprocess.run([uv, 'tool', 'install', '-U', tool])

# Use at your own risk, wax can't detect installed casks or Homebrew-added taps
# Installing wax casks may lead to `IO error: Permission denied (os error 13)`
# Using wax to uninstall and reinstall ruff or ty may lead to `IO error: File exists (os error 17)`
def wax_install(
    formulae: Optional[list[str]] = None,
    casks: Optional[list[str]] = None,
    taps: Optional[list[str]] = None,
    skip_update: bool = False
):
    """
    Install formulae and casks using Wax, a fast, modern Homebrew-compatible package manager built in Rust.

    Wax leverages Homebrew's ecosystem without the overhead and provides 16-20x faster search operations
    and parallel installation workflows while maintaining full compatibility with Homebrew formulae and bottles.
    """

    cargo = Path(which('cargo') or CARGO_HOME / 'bin' / 'cargo')
    if not cargo.is_file():
        info('Installing Rust...')
        subprocess.run(requests.get(RUSTUP_INSTALL_URL).text, shell=True)

    wax = Path(which('wax') or CARGO_HOME / 'bin' / 'wax')
    if not wax.is_file():
        info('Installing Wax...')
        subprocess.run([cargo, 'install', 'waxpkg'])
    elif not skip_update:
        subprocess.run([wax, 'update', '-s'])

    if taps:
        for tap in taps:
            subprocess.run([wax, 'tap', 'add', tap])
    if casks:
        subprocess.run([wax, 'c'] + casks)
    if formulae:
        subprocess.run([wax, 'i'] + formulae)

def zerobrew_install(
    formulae: Optional[list[str]] = None,
    casks: Optional[list[str]] = None,
    taps: Optional[list[str]] = None,
    skip_update: bool = False
):
    """
    Install Homebrew formulae and casks using the Zerobrew package manager.

    Zerobrew is a drop-in, 5-20x faster, experimental Homebrew alternative written in Rust.
    Zerobrew brings uv-style architecture to Homebrew packages on macOS and Linux.
    """

    zb = Path(which('zb') or XDG_BIN_HOME / 'zb')
    if not zb.is_file() or not skip_update:
        info('Installing Zerobrew...')
        subprocess.run(requests.get(ZEROBREW_INSTALL_URL).text, shell=True)

    if taps:
        # TODO: replace this when zerobrew supports taps
        error('Zerobrew does not support taps other than homebrew/core yet.')
    if casks:
        # Fall back to homebrew for now
        # TODO: replace this when zerobrew supports casks
        warn('Zerobrew does not support installing casks yet, falling back to Homebrew...')
        homebrew_install(casks=casks)
    if formulae:
        subprocess.run([zb, 'install'] + formulae)

# TODO: add support for other package managers
