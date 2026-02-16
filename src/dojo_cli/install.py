"""
Handles installing and updating package managers, and uses those managers to install and update packages and tools.
"""

from pathlib import Path
import requests
from shutil import which
import subprocess

from .log import error, info, warn

HOMEBREW_BIN_DIR = Path('/opt/homebrew/bin')
CARGO_BIN_DIR = Path('~/.cargo/bin').expanduser()
LOCAL_BIN_DIR = Path('~/.local/bin').expanduser()

HOMEBREW_INSTALL_URL = 'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh'
RUSTUP_INSTALL_URL = 'https://sh.rustup.rs'
SCOOP_INSTALL_URL = 'https://get.scoop.sh'
UV_INSTALL_URL = 'https://astral.sh/uv/install.sh'
ZEROBREW_GITHUB_URL = 'https://github.com/lucasgelfond/zerobrew'
ZEROBREW_INSTALL_URL = 'https://zerobrew.rs/install'

def homebrew_install(formulae: list[str] = [], casks: list[str] = [], taps: list[str] = []):
    """Install Homebrew formulae and casks."""

    brew = Path(which('brew') or HOMEBREW_BIN_DIR / 'brew')
    if not brew.is_file():
        info('Installing Homebrew...')
        subprocess.run(['bash', '-c', requests.get(HOMEBREW_INSTALL_URL).text])
    else:
        subprocess.run([brew, 'update'])

    if taps:
        for tap in taps:
            subprocess.run([brew, 'tap', tap])
    if casks:
        subprocess.run([brew, 'install', '--cask'] + casks)
    if formulae:
        subprocess.run([brew, 'install'] + formulae)

def scoop_install(packages: list[str] = [], buckets: list[str] = []):
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
    else:
        # TODO: Update scoop
        pass

    for bucket in buckets:
        subprocess.run(['scoop', 'bucket', 'add', bucket])
    for package in packages:
        subprocess.run(['scoop', 'install', package])

def uv_install(global_packages: list[str] = [], local_packages: list[str] = [], tools: list[str] = []):
    """
    Install Python packages and tools using uv, an extremely fast Python package manager written in Rust.
    This assumes that uv is installed independently and not with another package manager.
    """

    uv = Path(which('uv') or LOCAL_BIN_DIR / 'uv')
    if not uv.is_file():
        info('Installing uv...')
        subprocess.run(requests.get(UV_INSTALL_URL).text, shell=True)
    else:
        subprocess.run([uv, 'self', 'update'])

    if global_packages:
        subprocess.run([uv, 'pip', 'install', '-U', '--break-system-packages', '--strict', '--system'] + global_packages)
    elif local_packages:
        subprocess.run([uv, 'add', '-U'] + local_packages)
    if tools:
        for tool in tools:
            subprocess.run([uv, 'tool', 'install', '-U', tool])

# Use at your own risk, wax can't detect installed casks or Homebrew-added taps
# Installing wax casks may lead to `IO error: Permission denied (os error 13)`
# Using wax to uninstall and reinstall ruff or ty may lead to `IO error: File exists (os error 17)`
def wax_install(formulae: list[str] = [], casks: list[str] = [], taps: list[str] = []):
    """
    Install formulae and casks using Wax, a fast, modern Homebrew-compatible package manager built in Rust.

    Wax leverages Homebrew's ecosystem without the overhead and provides 16-20x faster search operations
    and parallel installation workflows while maintaining full compatibility with Homebrew formulae and bottles.
    """

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

    if taps:
        for tap in taps:
            subprocess.run([wax, 'tap', 'add', tap])
    if casks:
        subprocess.run([wax, 'c'] + casks)
    if formulae:
        subprocess.run([wax, 'i'] + formulae)

def zerobrew_install(formulae: list[str] = [], casks: list[str] = [], taps: list[str] = []):
    """
    Install Homebrew formulae and casks using the Zerobrew package manager.
    Zerobrew is a drop-in, 5-20x faster, experimental Homebrew alternative written in Rust.
    Zerobrew brings uv-style architecture to Homebrew packages on macOS and Linux.
    """

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

    if taps:
        error('Zerobrew does not support taps other than homebrew/core yet.')
    if casks:
        # Fall back to homebrew for now
        # TODO: replace this when zerobrew supports casks
        warn('Zerobrew does not support installing casks yet, falling back to Homebrew')
        homebrew_install(casks=casks)
    if formulae:
        subprocess.run([zb, 'install'] + formulae)

# TODO: add support for other package managers
