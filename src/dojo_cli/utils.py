"""
Utility functions for the pwn.college dojo CLI.
"""

from bs4 import BeautifulSoup
from cairosvg import svg2png
from io import BytesIO
from itsdangerous import URLSafeSerializer
import os
from pathlib import Path
import re
from requests import Session
from rich import box, print as rprint
from rich.table import Column, Table
from rich.text import Text
import string
from typing import Any

from .config import load_user_config
from .constants import TERM, TERM_PROGRAM
from .http import request
from .log import error, fail, info, success, warn
from .remote import ssh_getsize
from .terminal import apply_style

if TERM_PROGRAM not in ['Apple_Terminal']:
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

def get_challenge_id(dojo: str | None, module: str | None, challenge: str | None) -> int:
    if dojo and module and challenge:
        response = request(f'/{dojo}/{module}', False, False)
        soup = BeautifulSoup(response.text, 'html.parser')
        challenges = soup.find_all('div', class_='challenge-init')
        for challenge_div in challenges:
            input_challenge = challenge_div.find('input', id='challenge')
            if input_challenge and input_challenge['value'] == challenge:
                input_challenge_id = challenge_div.find('input', id='challenge-id')
                if input_challenge_id:
                    return int(str(input_challenge_id['value']))
    return -1

def parse_challenge_path(challenge: str, challenge_data: dict = {}) -> tuple:
    if re.fullmatch(r'[\-\w]+', challenge):
        if not challenge_data:
            challenge_data = request('/docker').json()
        if challenge_data.get('success'):
            return challenge_data.get('dojo'), challenge_data.get('module'), challenge
        return tuple()

    result = re.findall(r'/?([\-\~\w]+)/([\-\w]+)/([\-\w]+)', challenge)
    return result[0] if result else tuple()

def get_flag_size() -> int:
    flag_path = Path('/flag')

    if 'DOJO_AUTH_TOKEN' in os.environ:
        if flag_path.is_file():
            return flag_path.stat().st_size
        else:
            error('Flag file does not exist.')

    elif request('/docker').json().get('success'):
        flag_size = ssh_getsize(flag_path)
        if flag_size == -1:
            error('Flag file does not exist.')
        return flag_size

    else:
        error('No active challenge session; start a challenge!')

    return -1

def serialize_flag(account_id: int, challenge_id: int) -> str:
    return URLSafeSerializer('').dumps([account_id, challenge_id])[::-1]

def deserialize_flag(flag: str) -> list[int] | None:
    return URLSafeSerializer('').loads_unsafe(re.sub('.+?{(.+)}', r'\1', flag)[::-1])[1]

def get_box(s: str) -> box.Box | None:
    if hasattr(box, s) and isinstance(getattr(box, s), box.Box):
        return getattr(box, s)
    lines = s.splitlines()
    if len(lines) == 8 and all(len(line) == 4 for line in lines):
        return box.Box(s)

def show_table(table_data: dict[str, Any] | list[dict[str, Any]], title: str | None = None, keys: list[str] | None = None):
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
    table = Table(*map(get_column, keys), title=title, box=get_box(table_config['box']))
    [table.add_row(*[apply_style(row[key]) for key in keys]) for row in table_data]
    rprint(table)

def get_belt_hex(belt: str) -> str:
    return load_user_config()['belt_colors'][belt]

def can_render_image():
    if TERM in ['alacritty'] or TERM_PROGRAM in ['Apple_Terminal', 'tmux', 'WarpTerminal', 'zed']:
        return False
    if TERM in ['xterm-kitty'] or TERM_PROGRAM in ['ghostty', 'iTerm.app', 'vscode', 'WezTerm']:
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

def get_challenge_info(dojo: str | None = None, module: str | None = None, challenge: str | None = None):
    account_id = request('/users/me').json().get('id')
    if account_id is None:
        error('Please login first or run this in the dojo.')

    chal_data = request('/docker').json()

    if challenge:
        if not dojo or not module:
            challenge_path = parse_challenge_path(challenge, chal_data)
            if len(challenge_path) == 3 and all(isinstance(s, str) for s in challenge_path):
                dojo, module, challenge = challenge_path
            else:
                error('Invalid challenge ID.')
                return

        # verify that this challenge exists?
        challenge_id = get_challenge_id(dojo, module, challenge)
    else:
        if chal_data['success']:
            dojo, module, challenge = chal_data['dojo'], chal_data['module'], chal_data['challenge']
        else:
            error('No active challenge session; please start a challenge or specify a challenge name!')
            return

        active_module = request('/active-module', False)
        if active_module.is_redirect:
            challenge_id = get_challenge_id(dojo, module, challenge)
        else:
            challenge_id = active_module.json().get('c_current', {}).get('challenge_id', -1)

    return (dojo, module, challenge), (account_id, challenge_id)

def show_hint(dojo: str | None = None, module: str | None = None, challenge: str | None = None):
    (dojo, module, challenge), (account_id, challenge_id) = get_challenge_info(dojo, module, challenge)

    fake_flag = serialize_flag(account_id, challenge_id)
    flag_prefix = 'pwn.college{'
    flag_suffix = fake_flag[fake_flag.index('.'):] + '}'
    info(f'The flag starts with: [bold cyan]{flag_prefix}[/]')
    info(f'The flag ends with: [bold cyan]{flag_suffix}[/]')
    flag_chars = ''.join(sorted(string.digits + string.ascii_letters + '-_'))
    info(f'The middle of the flag can only be these characters: [bold cyan]{flag_chars}[/]')

    chal_data = request('/docker').json()
    if list(map(chal_data.get, ['dojo', 'module', 'challenge', 'practice'])) == [dojo, module, challenge, False]:
        flag_length = get_flag_size() - 1
        flag_path = Path('/flag')
        warn(f'The following information assumes that {apply_style(flag_path)} has not been tampered with:')
        info(f'Excluding the final newline, the flag is {flag_length} characters long.')
        middle_count = flag_length - len(flag_prefix) - len(flag_suffix)
        info(f'You only need to figure out the middle {middle_count} characters of the flag.')

    else:
        flag_length = len(f'pwn.college{{{fake_flag}}}')
        warn('You are not running the correct challenge in normal mode, so the real flag size cannot be measured.')
        info(f'Excluding the final newline, the flag is about {flag_length} characters long.')
        info(f'You would only need to figure out the middle {fake_flag.index('.')} characters of the flag.')

def submit_flag(flag: str | None = None, dojo: str | None = None, module: str | None = None, challenge: str | None = None):
    while not flag:
        flag = input('Enter the flag: ').strip()

    if flag in ['practice', 'pwn.college{practice}']:
        warn('This is the practice flag!')
        info('Restart the challenge in normal mode to get the real flag.')
        info('(You can do this with [bold]dojo restart [green]-n[/][/])')
        return

    (dojo, module, challenge), (account_id, challenge_id) = get_challenge_info(dojo, module, challenge)
    payload = deserialize_flag(flag)

    if isinstance(payload, list) and len(payload) == 2 and all(isinstance(i, int) for i in payload):
        if payload[0] != account_id:
            warn('This flag is from another account! Are you sure you want to submit?')
            if input('(y/N) > ').strip()[0].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

        if payload[1] != challenge_id:
            warn('This flag is from another challenge! Are you sure you want to submit?')
            if input('(y/N) > ').strip()[0].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

        chal_data = request('/docker').json()
        if list(map(chal_data.get, ['dojo', 'module', 'challenge', 'practice'])) == [dojo, module, challenge, False]:
            flag_length = get_flag_size() - 1
        else:
            flag_length = len(f'pwn.college{{{serialize_flag(account_id, challenge_id)}}}')

        full_flag_mismatch = re.fullmatch(r'pwn.college{[\-\.\w]+}', flag) and len(flag) != flag_length
        partial_flag_mismatch = re.fullmatch(r'[\-\.\w]+', flag) and len(f'pwn.college{{{flag}}}') != flag_length
        if full_flag_mismatch or partial_flag_mismatch:
            warn(f'This flag is the wrong size! The real flag length is {flag_length}. Are you sure you want to submit?')
            if input('(y/N) > ').strip()[0].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

    else:
        warn('Could not deserialize flag. Are you sure you want to submit?')
        if input('(y/N) > ').strip()[0].lower() != 'y':
            warn('Aborting flag submission attempt!')
            return

    info(f'Submitting the flag: {flag}')

    # TODO: Tell user if the flag is correct even if the challenge is already solved
    # I fixed this already in CTFd (https://github.com/CTFd/CTFd/pull/2651) but pwn.college never merged it
    #
    # response = request(
    #     '/api/v1/challenges/attempt',
    #     False,
    #     csrf='DOJO_AUTH_TOKEN' not in os.environ,
    #     json={'challenge_id': challenge_id, 'submission': flag}
    # )
    # rprint(response.json().get('data').get('message'))

    response = request(
        f'/dojos/{dojo}/{module}/{challenge}/solve',
        csrf='DOJO_AUTH_TOKEN' not in os.environ,
        json={'submission': flag}
    )

    result = response.json()

    if response.ok:
        if result.get('status') == 'solved':
            success('The flag is correct! You have successfully solved the challenge!')
        elif result.get('status') == 'already_solved':
            warn('You have already solved this challenge!')
        else:
            info(str(result))
    elif response.status_code == 400:
        if result.get('status') == 'incorrect':
            fail('The flag is incorrect.')
        else:
            error(str(result))
    elif response.status_code == 404:
        if result.get('error') == 'Challenge not found':
            error('The challenge does not exist.')
        else:
            error(str(result))
    else:
        error(f'Failed to submit the flag (code: {response.status_code}).')
