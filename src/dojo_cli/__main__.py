"""
This is here just so you can run `python -m dojo_cli` instead of `dojo` if you want to do that for some reason.
"""

import sys
from .cli import app

if __name__ == '__main__':
    sys.exit(app())
