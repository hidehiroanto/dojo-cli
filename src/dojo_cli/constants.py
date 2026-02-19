"""
Constants for the pwn.college dojo CLI.
"""

from pathlib import Path
import platform
import os

CARGO_HOME = Path('~/.cargo').expanduser()
SSH_HOME = Path('~/.ssh').expanduser()

UNAME_MACHINE = platform.machine()
UNAME_SYSTEM = platform.system()

XDG_BIN_HOME = Path(os.getenv('XDG_BIN_HOME', '~/.local/bin')).expanduser()
XDG_CACHE_HOME = Path(os.getenv('XDG_CACHE_HOME', '~/.cache')).expanduser()
XDG_CONFIG_HOME = Path(os.getenv('XDG_CONFIG_HOME', '~/.config')).expanduser()
XDG_DATA_HOME = Path(os.getenv('XDG_DATA_HOME', '~/.local/share')).expanduser()
