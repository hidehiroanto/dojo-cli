"""Constants for the pwn.college dojo CLI."""

from pathlib import Path
import platform
import os

CARGO_HOME = Path('~/.cargo')
SSH_HOME = Path('~/.ssh')

UNAME_MACHINE = platform.machine()
UNAME_SYSTEM = platform.system()

XDG_BIN_HOME = Path(os.getenv('XDG_BIN_HOME', '~/.local/bin'))
XDG_CACHE_HOME = Path(os.getenv('XDG_CACHE_HOME', '~/.cache'))
XDG_CONFIG_HOME = Path(os.getenv('XDG_CONFIG_HOME', '~/.config'))
XDG_DATA_HOME = Path(os.getenv('XDG_DATA_HOME', '~/.local/share'))
