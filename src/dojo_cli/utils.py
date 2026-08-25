"""Utility functions for the pwn.college dojo CLI."""

import os
import re
from collections.abc import Iterable
from functools import lru_cache
from io import BytesIO
from typing import Any

from cairosvg import svg2png
from rich import box
from rich import print as rprint
from rich.table import Column, Table
from rich.text import Text

from .config import load_user_config
from .http import request
from .log import error
from .terminal import apply_style

if os.getenv('TERM_PROGRAM') not in ['Apple_Terminal']:
    from textual_image.renderable import Image, SixelImage, TGPImage

def fix_markdown_links(markdown: str) -> str:
    return re.sub(r'\[([^\]]+)\]\((\/[^\)]+)\)', fr'[\1]({load_user_config()['base_url']}\2)', markdown)

def paginate(items: list, page: int | None, page_size: int = 20) -> list:
    """Return a one-based page of items."""
    if page is None:
        return items
    if page < 1:
        error('Page numbers start at 1.')
    start = (page - 1) * page_size
    return items[start:start + page_size]

def require_item(items: Iterable[dict], item_id: str, item_type: str) -> dict:
    """Return an item by ID or exit with a descriptive error."""
    item = next((item for item in items if item.get('id') == item_id), None)
    if item is None:
        error(f'{item_type} {item_id} does not exist.')
    return item

def get_box(s: str) -> box.Box | None:
    if hasattr(box, s) and isinstance(getattr(box, s), box.Box):
        return getattr(box, s)
    lines = s.splitlines()
    if len(lines) == 8 and all(len(line) == 4 for line in lines):
        return box.Box(s)

def show_table(table_data: dict[str, Any] | list[dict[str, Any]], title: str | None = None, keys: list[str] | None = None, **kwargs):
    if isinstance(table_data, dict):
        table_data = [table_data]
    if not table_data:
        rprint(f'[dim]{title or 'Results'}: no results[/]')
        return
    if not keys:
        keys = list(table_data[0])

    table_config = load_user_config()['table']
    def get_column(key: str) -> Column:
        return Column(Text(
            key.upper() if key in ['id', 'url'] else key.replace('_', ' ').title(),
            table_config['column']['style'],
            justify=table_config['column']['justify']
        ))
    table = Table(*map(get_column, keys), title=title, box=get_box(table_config['box']), **kwargs)
    [table.add_row(*[apply_style(row[key]) for key in keys]) for row in table_data]
    rprint(table)

def get_belt_hex(belt: str | None) -> str:
    return load_user_config()['belt_colors'].get(belt)

def can_render_image():
    term, term_program = os.getenv('TERM'), os.getenv('TERM_PROGRAM')
    if term in ['alacritty'] or term_program in ['Apple_Terminal', 'tmux', 'WarpTerminal', 'zed']:
        return False
    if term in ['xterm-kitty'] or term_program in ['ghostty', 'iTerm.app', 'vscode', 'WezTerm']:
        return True
    return issubclass(Image, (SixelImage, TGPImage))

@lru_cache(maxsize=128)
def download_image_bytes(url: str) -> bytes:
    if url.endswith('.svg'):
        return svg2png(url=url)
    return request(url, False, False).content

def download_image(url: str, height: int = 1):
    base_url = load_user_config()['base_url']
    if not url.startswith(('http://', 'https://')):
        url = base_url + url
    image = download_image_bytes(url)
    return Image(BytesIO(image), 'auto', height)
