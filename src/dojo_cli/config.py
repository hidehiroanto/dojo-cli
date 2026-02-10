"""
Handles config. Config can be either JSON or YAML for now, might add TOML later.
"""

from copy import deepcopy
import json
from os import getenv
from pathlib import Path
from rich import print as rprint
from sys import stderr
import yaml

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
    'cookie_path': '~/.cache/dojo-cli/cookie.json',
    'log_styles': {
        'error': 'on red',
        'fail': 'bold red',
        'info': 'bold blue',
        'success': 'bold green',
        'warn': 'bold yellow'
    },
    'object_styles': {
        'False': 'italic red',
        'None': 'italic magenta',
        'True': 'italic green',
        'bytes': 'green',
        'float': 'bold cyan',
        'int': 'bold cyan',
        'link': 'cyan',
        'rank': 'bold green'
    },
    'ssh': {
        'Host': 'pwn.college',
        'HostName': 'dojo.pwn.college',
        'Port': 22,
        'User': 'hacker',
        'IdentityFile': '~/.ssh/id_ed25519',
        'ServerAliveInterval': 20,
        'ServerAliveCountMax': 3,
        'algorithm': 'ed25519',
        'config_file': '~/.ssh/config',
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

DEFAULT_CONFIG_PATH = '~/.config/dojo-cli/config'

user_config = {}

def load_config(config_path: Path):
    config_path = config_path.expanduser()
    if not config_path.is_absolute():
        config_path = Path.home() / config_path
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
        rprint(f'Error loading config file at `{config_path}`: {e}', file=stderr)
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
        config_path = Path(getenv('DOJO_CONFIG', DEFAULT_CONFIG_PATH)).expanduser()
        user_config = deepmerge(DEFAULT_CONFIG, load_config(config_path))
    return user_config

def display_config(default: bool = False):
    rprint(json.dumps(DEFAULT_CONFIG if default else load_user_config(), indent=4))
