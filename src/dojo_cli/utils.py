"""
Utility functions for the pwn.college dojo CLI.
"""

from cairosvg import svg2png
from io import BytesIO
import os
from rich import box, print as rprint
from rich.table import Column, Table
from rich.text import Text
from typing import Any

from .config import load_user_config
from .http import request
from .terminal import apply_style

if os.getenv('TERM_PROGRAM') not in ['Apple_Terminal']:
    from textual_image.renderable import Image, SixelImage, TGPImage

def get_box(s: str) -> box.Box | None:
    if hasattr(box, s) and isinstance(getattr(box, s), box.Box):
        return getattr(box, s)
    lines = s.splitlines()
    if len(lines) == 8 and all(len(line) == 4 for line in lines):
        return box.Box(s)

def show_table(table_data: dict[str, Any] | list[dict[str, Any]], title: str | None = None, keys: list[str] | None = None, **kwargs):
    if isinstance(table_data, dict):
        table_data = [table_data]
    if not keys:
        keys = list(table_data[0].keys())

    table_config = load_user_config()['table']
    def get_column(key: str) -> Column:
        return Column(Text(
            'ID' if key == 'id' else key.replace('_', ' ').title(),
            table_config['column']['style'],
            justify=table_config['column']['justify']
        ))
    table = Table(*map(get_column, keys), title=title, box=get_box(table_config['box']), **kwargs)
    [table.add_row(*[apply_style(row[key]) for key in keys]) for row in table_data]
    rprint(table)

def get_belt_hex(belt: str) -> str:
    return load_user_config()['belt_colors'][belt]

def can_render_image():
    term, term_program = os.getenv('TERM'), os.getenv('TERM_PROGRAM')
    if term in ['alacritty'] or term_program in ['Apple_Terminal', 'tmux', 'WarpTerminal', 'zed']:
        return False
    if term in ['xterm-kitty'] or term_program in ['ghostty', 'iTerm.app', 'vscode', 'WezTerm']:
        return True
    return issubclass(Image, (SixelImage, TGPImage))

def download_image(url: str, image_type: str | None = None):
    base_url = load_user_config()['base_url']
    if not (url.startswith('http://') or url.startswith('https://')):
        url = base_url + url

    image = svg2png(url=url) if url.endswith('.svg') else request(url, False, False).content
    aspect_ratios = {'belt': 6, 'flag': 3, 'symbol': 2}
    return Image(BytesIO(image), aspect_ratios.get(image_type, 2), 1)
