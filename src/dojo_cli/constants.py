"""
Constants for the pwn.college dojo CLI.
"""

from os import getenv
from pathlib import Path

FLAG_PATH = Path('/flag')
TERM = getenv('TERM', '')
TERM_PROGRAM = getenv('TERM_PROGRAM', '')
