"""
Handles logging.
"""

from rich import print as rprint
import sys

from .config import load_user_config

def format_message(message_type: str, symbol: str, message: str):
    return f'[[{load_user_config()['log_styles'][message_type]}]{symbol}[/]] {message}'

def error(message: str, **kwargs):
    file = kwargs.pop('file', sys.stderr)
    rprint(format_message('error', 'ERROR', message), file=file, **kwargs)
    exit(1)

def fail(message: str, **kwargs):
    rprint(format_message('fail', '-', message), **kwargs)

def info(message: str, **kwargs):
    rprint(format_message('info', '*', message), **kwargs)

def success(message: str, **kwargs):
    rprint(format_message('success', '+', message), **kwargs)

def warn(message: str, **kwargs):
    rprint(format_message('warn', '!', message), **kwargs)
