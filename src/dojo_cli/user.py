"""
Handles user login and data.
"""

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from getpass import getpass
import re
from requests import Session
from rich import print as rprint
from rich.table import Table
from typing import Optional

from .config import load_user_config
from .http import delete_cookie, request, save_cookie
from .log import error, fail, info, success
from .utils import can_render_image, download_image, get_belt_hex, show_table

def do_register(username: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None):
    while not username:
        username = input('Enter username: ')
    while not email:
        email = input('Enter email: ')
    while not password:
        password = getpass('Enter password: ', echo_char=load_user_config()['password_echo_char'])

    with Session() as session:
        credentials = {'name': username, 'email': email, 'password': password, 'commitment_verified': 'verified'}
        response = request('/register', False, False, True, session=session, data=credentials)
        errors = re.findall(r'<div class=".*" role="alert">\s+<span>(.*)</span>', response.text)

        if errors:
            for error_msg in errors:
                fail(error_msg)
        else:
            save_cookie({'session': session.cookies.get('session')})
            success(f'Registered and logged in as user [b green]{username}[/]!')

def do_login(username: Optional[str] = None, password: Optional[str] = None):
    while not username:
        username = input('Enter username or email: ')
    while not password:
        password = getpass('Enter password: ', echo_char=load_user_config()['password_echo_char'])

    with Session() as session:
        credentials = {'name': username, 'password': password}
        response = request('/login', False, False, True, session=session, data=credentials)
        errors = re.findall(r'<div class=".*" role="alert">\s+<span>(.*)</span>', response.text)

        if errors:
            for error_msg in errors:
                fail(error_msg)
        else:
            save_cookie({'session': session.cookies.get('session')})
            success(f'Logged in as user [b green]{username}[/]!')

def do_logout():
    delete_cookie()
    success('You have logged out.')

def change_settings():
    settings = request('/settings', False).text
    matches = re.findall(r'<input class="form[^"]*" id="(\w+)" name="\w+" (type="\w+")? value="([^"]*)">', settings)
    old_data = [match for match in matches if match[0] not in {'confirm', 'expiration'}]
    new_data = {}
    for key, value in old_data:
        if key != 'password':
            info(f'Old {key}: {value}')
        info(f'Change {key}?')
        if input('(y/N) > ').strip()[:1].lower() == 'y':
            if key == 'password':
                password_echo_char = load_user_config()['password_echo_char']
                new_data['confirm'] = getpass('Confirm old password: ', echo_char=password_echo_char)
                new_data['password'] = getpass('Enter new password: ', echo_char=password_echo_char)
            else:
                info(f'Enter new {key}:')
                new_data[key] = input()

    response = request('/api/v1/users/me', False, method='PATCH', data=new_data).json()
    if response.get('success'):
        success('Success! Your profile has been updated.')
    elif response.get('errors', {}):
        if response['errors'].get('confirm'):
            error(response['errors']['confirm'])
        else:
            error(str(response['errors']))

def get_rank(num):
    rank_style = load_user_config()['object_styles']['rank']
    return '🥇🥈🥉'[num - 1] if num < 4 else f'[{rank_style}]{num}[/]'

def show_me(simple: bool = False):
    me = request('/users/me')
    account = me.json()
    if not me.ok:
        error(account.get('error', 'Unknown error'))

    score = request('/score', auth=False, params={'username': account['name']})
    fields = list(map(int, score.json().split(':')))

    belt_data = request('/belts', auth=False).json()['users'].get(str(account['id']), {})
    belt_hex = get_belt_hex(belt_data.get('color', 'white'))

    account['rank'] = f'[b green]{get_rank(fields[0])}/{fields[5]}[/]'
    account['handle'] = f'[b {belt_hex}]{account['name']}[/]'
    if not simple and can_render_image():
        account['belt'] = download_image(f'/belt/{belt_data['color']}.svg', 'belt')
    else:
        account['belt'] = f'[b {belt_hex}]{belt_data['color'].title()}[/]'
    account['country'] = ''.join(chr(ord(c) + ord('🇦') - ord('A')) for c in account['country'])
    account['date_ascended'] = datetime.fromisoformat(belt_data['date'])
    account['score'] = f'[b cyan]{fields[1]}/{fields[2]}[/]'

    info(f'You are the epic hacker [b green]{account['name']}[/]!')
    keys = ['rank', 'id', 'handle', 'belt', 'email', 'website', 'affiliation', 'country', 'bracket', 'date_ascended', 'score']
    show_table(account, 'Account Info', keys)

def show_score(username: Optional[str] = None):
    if not username:
        me = request('/users/me')
        if me.ok:
            username = me.json().get('name')
        else:
            error(me.json().get('error', 'Unknown error'))

    score = request('/score', auth=False, params={'username': username}).json()
    fields = list(map(int, score.split(':')))

    show_table({
        'rank': f'[b green]{get_rank(fields[0])}/{fields[5]}[/]',
        'handle': f'[b green]{username}[/]',
        'score': f'[b cyan]{fields[1]}/{fields[2]}[/]'
    }, 'Global ranking')

def show_activity(user_id: Optional[int] = None):
    if user_id is None:
        user_id = request('/users/me').json().get('id')
    if user_id < 0:
        error(f'User ID {user_id} is invalid.')

    activity = request(f'/activity/{user_id}', auth=False).json()
    if activity.get('success'):
        timestamps = list(map(datetime.fromisoformat, activity['data']['solve_timestamps']))
        if not timestamps:
            fail(f'No solves in the last year for user with ID {user_id}.')
            return
        frequencies = [[0 for _ in range(53)] for _ in range(7)]
        heatmap = [[' ' for _ in range(55)] for _ in range(7)]
        first_monday = min(timestamps) - timedelta(min(timestamps).weekday())
        max_frequency = 0
        for week in range(53):
            for day in range(7):
                current_date = first_monday + timedelta(week * 7 + day)
                frequencies[day][week] = sum(1 if d.date() == current_date.date() else 0 for d in timestamps)
                max_frequency = max(max_frequency, frequencies[day][week])

        table = Table(*['' for _ in range(56)], title='Hacking Activity', box=None, padding=0)
        for week in range(53):
            for day in range(7):
                current_date = first_monday + timedelta(week * 7 + day)
                if current_date.day == 1:
                    for i, month_char in enumerate(current_date.strftime('%b')):
                        table.columns[week + i + 1].header = month_char
                redblue = int(0x80 - 0x80 * frequencies[day][week] / max_frequency)
                green = int(0x80 + 0x7f * frequencies[day][week] / max_frequency)
                heatmap[day][week] = f'[#{redblue:02x}{green:02x}{redblue:02x}]■[/]'

        for day_name, row in zip(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], heatmap):
            table.add_row(day_name + ' ', *row)
        rprint(table)

    else:
        error(f'User not found for ID {user_id}.')

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
            row['country'] = f'[b]{country}[/]'

        row['username'] = f'[b]{tds[2].string}[/]'
        row['score'] = int(tds[3].string or 0)
        row['percentage'] = f'[b cyan]{tds[4].string}[/]'
        wechall_data.append(row)

    return wechall_data

def show_scoreboard(dojo_id: Optional[str] = None, module_id: Optional[str] = None, duration: str = 'all', page: int = 1, simple: bool = False):
    if dojo_id:
        durations = {'week': 7, 'month': 30, 'all': 0}
        endpoint = f'/scoreboard/{dojo_id}/{module_id or '_'}/{durations.get(duration.lower(), 0)}/{page}'
        standings = request(endpoint, auth=False).json().get('standings')
        images = {}
        render_image = not simple and can_render_image()

        for row in standings:
            belt = row['belt'].split('/')[-1].split('.')[0]
            symbol = row['symbol'].split('/')[-1].split('.')[0]
            belt_hex = get_belt_hex(belt)

            row['rank'] = get_rank(row['rank'])
            row['handle'] = f'[b {belt_hex}]{row['name']}[/]'
            row['badges'] = ''.join(sorted(badge['emoji'] for badge in row['badges']))

            if render_image:
                if belt not in images:
                    images[belt] = download_image(row['belt'], 'belt')
                row['belt'] = images[belt]

                if symbol not in images:
                    images[symbol] = download_image(row['symbol'])
                row['role'] = images[symbol]
            else:
                row['belt'] = f'[b {belt_hex}]{belt.title()}[/]'
                row['role'] = 'ASU Student' if symbol == 'fork' else symbol.title()

        title = f'Scoreboard for [b]{f'{dojo_id}/{module_id}' if module_id else dojo_id}[/]'
        show_table(standings, title, ['rank', 'role', 'handle', 'belt', 'badges', 'solves'])

    else:
        show_table(get_wechall_rankings(page, simple), 'WeChall rankings')

def show_belts(belt: Optional[str] = None, page: Optional[int] = None, simple: bool = False):
    response = request('/belts', auth=False).json()

    render_image = not simple and can_render_image()
    if render_image:
        if belt in response['ranks']:
            images = {belt: download_image(f'/belt/{belt}.svg', 'belt')}
        else:
            images = {belt: download_image(f'/belt/{belt}.svg', 'belt') for belt in response['ranks']}

    belts = []
    if belt in response['ranks']:
        belt_hex = get_belt_hex(belt)
        title = f'[b {belt_hex}]Belted Hackers[/]'
        for rank, id in enumerate(response['ranks'][belt]):
            user = response['users'][str(id)]
            user['rank'] = f'[b green]{get_rank(rank + 1)}/{len(response['ranks'][belt])}[/]'
            user['id'] = id
            user['handle'] = f'[b {belt_hex}]{user['handle']}[/]'
            if render_image:
                user['belt'] = images[belt]
            else:
                user['belt'] = f'[b {belt_hex}]{user['color'].title()}[/]'
            user['website'] = user['site']
            user['date_ascended'] = user['date']
            user['date_ascended'] = datetime.fromisoformat(user['date'])
            belts.append(user)
    else:
        title = '[b]Belted Hackers[/]'
        for rank, (id, user) in enumerate(response['users'].items()):
            belt_hex = get_belt_hex(user['color'])
            user['rank'] = f'[b green]{get_rank(rank + 1)}/{len(response['users'])}[/]'
            user['id'] = int(id)
            user['handle'] = f'[b {belt_hex}]{user['handle']}[/]'
            if render_image:
                user['belt'] = images[user['color']]
            else:
                user['belt'] = f'[b {belt_hex}]{user['color'].title()}[/]'
            user['website'] = user['site']
            user['date_ascended'] = datetime.fromisoformat(user['date'])
            belts.append(user)

    if page is not None:
        belts = belts[page * 20:][:20]
    show_table(belts, title, ['rank', 'id', 'handle', 'belt', 'website', 'date_ascended'])
