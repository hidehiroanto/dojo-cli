"""
Handles configuration. Configuration file can be either JSON or YAML for now, might add TOML later.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
from rich import print as rprint
import sys
import yaml

from .constants import SSH_HOME, XDG_CACHE_HOME, XDG_CONFIG_HOME, XDG_DATA_HOME

DEFAULT_CONFIG = {
    'api': '/pwncollege_api/v1',
    'base_url': 'https://pwn.college',
    'belt_colors': {
        'white': '#f0f0f0',
        'orange': '#ff7f32',
        'yellow': '#ffc627',
        'green': '#78be20',
        'blue': '#00a3e0',
        'purple': '#7b2f8e',
        'black': '#111111'
    },
    'cookie_path': str(XDG_CACHE_HOME / 'dojo-cli' / 'cookie.json'),
    'editor': 'Visual Studio Code',
    'log_styles': {
        'error': 'on red',
        'fail': 'bold red',
        'info': 'bold blue',
        'success': 'bold green',
        'warn': 'bold yellow'
    },
    'object_styles': {
        'False': 'bold italic bright_red',
        'None': 'bold italic magenta',
        'True': 'bold italic bright_green',
        'bytes': 'green',
        'date': 'bold blue',
        'email': 'bright_cyan',
        'float': 'bold cyan',
        'int': 'bold cyan',
        'filename': 'bold bright_magenta',
        'path': 'bold magenta',
        'rank': 'bold green',
        'time': 'bold magenta',
        'url': 'bright_blue'
    },
    'package_manager': {
        'Darwin': 'homebrew',
        'Linux': 'homebrew',
        'Windows': 'scoop'
    },
    'password_echo_char': '*',
    'ssh': {
        'Host': 'pwn.college',
        'HostName': 'dojo.pwn.college',
        'Port': 22,
        'User': 'hacker',
        'IdentityFile': str(SSH_HOME / 'id_ed25519'),
        'ServerAliveInterval': 20,
        'ServerAliveCountMax': 3,
        'config_file': str(SSH_HOME / 'config'),
        'mount_point': str(XDG_DATA_HOME / 'dojo-cli' / 'mnt'),
        'project_path': '/home/hacker'
    },
    'table': {
        'box': 'ROUNDED',
        'column': {
            'justify': 'center',
            'style': 'green'
        },
    }
}

DEFAULT_CONFIG_PATH = XDG_CONFIG_HOME / 'dojo-cli' / 'config'

user_config = {}

def load_config(config_path: Path):
    config_path = config_path.expanduser().resolve()
    if config_path.is_dir():
        config_path /= 'config'
    if not config_path.is_file():
        return {}
    try:
        config_data = config_path.read_text()
        if not config_data:
            return {}
        return yaml.safe_load(config_data)
    except Exception as e:
        rprint(f'[[on red]ERROR[/]] Error loading config file at [bold]{config_path}[/]: {e}', file=sys.stderr)
        exit(1)

def deepmerge(dst_dict: dict, src_dict: dict) -> dict:
    final_dict = deepcopy(dst_dict)
    for key in src_dict:
        if key in dst_dict and isinstance(dst_dict[key], dict) and isinstance(src_dict[key], dict):
            final_dict[key] = deepmerge(dst_dict[key], src_dict[key])
        elif key in dst_dict and isinstance(dst_dict[key], list) and isinstance(src_dict[key], list):
            final_dict[key] = sorted(list(set(deepcopy(dst_dict[key]) + deepcopy(src_dict[key]))))
        else:
            final_dict[key] = deepcopy(src_dict[key])
    return final_dict

def load_user_config() -> dict:
    """Load user config from config path, then deep merge it with default config."""

    global user_config
    if not user_config:
        config_path = Path(os.getenv('DOJO_CONFIG', DEFAULT_CONFIG_PATH))
        user_config = deepmerge(DEFAULT_CONFIG, load_config(config_path))
    return user_config

def show_config(show_default: bool = False):
    rprint(json.dumps(DEFAULT_CONFIG if show_default else load_user_config(), indent=4))
