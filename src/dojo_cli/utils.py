"""
Utility functions for the pwn.college dojo CLI.
"""

from bs4 import BeautifulSoup
from cairosvg import svg2png
from io import BytesIO
import os
from requests import Session
from rich import box, print as rprint
from rich.table import Column, Table
from rich.text import Text
from typing import Any

from .config import load_user_config
from .http import request
from .terminal import apply_style

if os.getenv('TERM_PROGRAM') not in ['Apple_Terminal']:
    from textual_image.renderable import Image, SixelImage, TGPImage

def get_rank(num):
    rank_style = load_user_config()['object_styles']['rank']
    return '🥇🥈🥉'[num - 1] if num < 4 else f'[{rank_style}]{num}[/]'

def get_wechall_rankings(page: int = 1, simple: bool = False):
    render_image = not simple and can_render_image()
    wechall_html = request(f'https://www.wechall.net/site/ranking/for/104/pwn_college/page-{page}', auth=False)
    soup = BeautifulSoup(wechall_html.text, 'html.parser')
    images = {}
    wechall_data = []

    for tr in soup.find_all('tr')[2:]:
        tds = tr.find_all('td')
        row = {'rank': get_rank(int(tds[0].string or 0))}

        img_alt = tds[1].img['alt'] if tds[1].img else ''
        country = 'Unknown' if img_alt == '__Unknown Country' else img_alt
        if render_image:
            if country not in images:
                img_src = str(tds[1].img['src']) if tds[1].img else ''
                images[country] = download_image('https://www.wechall.net' + img_src, 'flag')
            row['country'] = images[country]
        else:
            row['country'] = f'[bold]{country}[/]'

        row['username'] = f'[bold]{tds[2].string}[/]'
        row['score'] = int(tds[3].string or 0)
        row['percentage'] = f'[bold cyan]{tds[4].string}[/]'
        wechall_data.append(row)

    return wechall_data

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

    if url.endswith('.svg'):
        image = svg2png(url=url)
    else:
        with Session() as session:
            image = session.get(url).content

    aspect_ratios = {'belt': 6, 'flag': 3, 'symbol': 2}
    return Image(BytesIO(image), aspect_ratios.get(image_type, 2), 1)
