"""Handle JSON and YAML configuration files."""

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import yaml
from rich import print as rprint

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
        'black': '#111111',
    },
    'cookie_path': str(XDG_CACHE_HOME.expanduser() / 'dojo-cli' / 'cookie.json'),
    'editor': 'Visual Studio Code',
    'mount': {'implementation': 'sshfs', 'provider': 'auto'},
    'log_styles': {
        'error': 'on red',
        'fail': 'b red',
        'info': 'b blue',
        'success': 'b green',
        'warn': 'b yellow',
    },
    'object_styles': {
        'False': 'b i bright_red',
        'None': 'b i magenta',
        'True': 'b i bright_green',
        'bytes': 'green',
        'date': 'b blue',
        'email': 'bright_cyan',
        'float': 'b cyan',
        'int': 'b cyan',
        'filename': 'b bright_magenta',
        'path': 'b magenta',
        'rank': 'b green',
        'time': 'b magenta',
        'url': 'bright_blue',
    },
    'package_manager': {'Darwin': 'homebrew', 'Linux': 'homebrew', 'Windows': 'scoop'},
    'password_echo_char': '*',
    'ssh': {
        'Host': 'pwn.college',
        'HostName': 'dojo.pwn.college',
        'Port': 22,
        'User': 'hacker',
        'IdentityFile': str(SSH_HOME.expanduser() / 'id_ed25519'),
        'ServerAliveInterval': 20,
        'ServerAliveCountMax': 3,
        'config_file': str(SSH_HOME.expanduser() / 'config'),
        'mount_point': str(XDG_DATA_HOME.expanduser() / 'dojo-cli' / 'mnt'),
        'project_path': '/home/hacker',
    },
    'table': {
        'box': 'ROUNDED',
        'column': {'justify': 'center', 'style': 'green'},
    },
}

DEFAULT_CONFIG_PATH = XDG_CONFIG_HOME / 'dojo-cli' / 'config'

user_config = {}


def load_config(config_path: Path) -> object:
    config_path = config_path.expanduser().resolve()
    if config_path.is_dir():
        config_path /= 'config'
    if not config_path.is_file():
        return {}
    try:
        config_data = config_path.read_text()
        if not config_data:
            return {}
        parsed = yaml.safe_load(config_data)
        return {} if parsed is None else parsed
    except (OSError, yaml.YAMLError) as e:
        rprint(
            f'[[on red]ERROR[/]] Error loading config file at [b]{config_path}[/]: {e}',
            file=sys.stderr,
        )
        sys.exit(1)


def validate_config(config: object, defaults: dict, path: str = '') -> list[str]:
    """Validate known configuration keys while allowing extensions."""
    if not isinstance(config, dict):
        location = path or 'configuration'
        return [f'{location} must be an object, not {type(config).__name__}']

    errors = []
    for key, value in config.items():
        if key not in defaults:
            continue
        location = f'{path}.{key}' if path else str(key)
        default = defaults[key]
        if isinstance(default, dict):
            errors.extend(validate_config(value, default, location))
        elif type(value) is not type(default):
            errors.append(
                f'{location} must be {type(default).__name__}, '
                f'not {type(value).__name__}'
            )
    return errors


def report_config_errors(config_path: Path, errors: list[str]):
    """Report configuration validation failures and exit."""
    rprint(
        f'[[on red]ERROR[/]] Invalid config file at [b]{config_path}[/]:',
        file=sys.stderr,
    )
    for message in errors:
        rprint(f'  - {message}', file=sys.stderr)
    sys.exit(1)


def deepmerge(dst_dict: dict, src_dict: dict) -> dict:
    final_dict = deepcopy(dst_dict)
    for key, value in src_dict.items():
        if (
            key in dst_dict
            and isinstance(dst_dict[key], dict)
            and isinstance(value, dict)
        ):
            final_dict[key] = deepmerge(dst_dict[key], value)
        elif (
            key in dst_dict
            and isinstance(dst_dict[key], list)
            and isinstance(value, list)
        ):
            final_dict[key] = sorted(set(deepcopy(dst_dict[key]) + deepcopy(value)))
        else:
            final_dict[key] = deepcopy(value)
    return final_dict


def load_user_config() -> dict:
    """Load user config from config path, then deep merge it with default config."""

    global user_config
    if not user_config:
        config_path = Path(os.getenv('DOJO_CONFIG', DEFAULT_CONFIG_PATH))
        loaded = load_config(config_path)
        errors = validate_config(loaded, DEFAULT_CONFIG)
        if errors:
            report_config_errors(config_path, errors)
        assert isinstance(loaded, dict)
        user_config = deepmerge(DEFAULT_CONFIG, loaded)
    return user_config


def show_config(show_default: bool = False):
    rprint(json.dumps(DEFAULT_CONFIG if show_default else load_user_config(), indent=4))
