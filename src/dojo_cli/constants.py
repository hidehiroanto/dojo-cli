"""
Constants for the pwn.college dojo CLI.
"""

from os import getenv
from pathlib import Path

DOJO_AUTH_TOKEN = getenv('DOJO_AUTH_TOKEN', '')
FLAG_PATH = Path('/flag')
TERM = getenv('TERM', '')
TERM_PROGRAM = getenv('TERM_PROGRAM', '')
