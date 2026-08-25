"""Allow running `python -m dojo_cli` instead of `dojo`."""

import sys

from .cli import app

if __name__ == '__main__':
    sys.exit(app())
