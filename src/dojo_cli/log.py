"""
Handles logging.
"""

from rich import print as rprint
from sys import stderr

from .config import load_user_config

def format_message(message_type: str, symbol: str, message: str):
    return f'[[{load_user_config()['log_styles'][message_type]}]{symbol}[/]] {message}'

def error(message: str):
    rprint(format_message('error', 'ERROR', message), file=stderr)
    exit(1)

def fail(message: str):
    rprint(format_message('fail', '-', message))

def info(message: str):
    rprint(format_message('info', '*', message))

def success(message: str):
    rprint(format_message('success', '+', message))

def warn(message: str):
    rprint(format_message('warn', '!', message))
