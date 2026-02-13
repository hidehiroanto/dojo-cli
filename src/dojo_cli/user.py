"""
Handles user login and data.
"""

from bs4 import BeautifulSoup
from datetime import datetime
from getpass import getpass
from requests import Session

from .config import load_user_config
from .http import delete_cookie, request, save_cookie
from .log import error, fail, info, success
from .utils import can_render_image, download_image, get_belt_hex, show_table

def do_login(username: str | None = None, password: str | None = None):
    while not username:
        username = input('Enter username or email: ')
    while not password:
        password = getpass('Enter password: ', echo_char=load_user_config()['echo_char'])

    with Session() as session:
        credentials = {'name': username, 'password': password}
        response = request('/login', False, False, True, session=session, data=credentials)

        if 'Your username or password is incorrect' in response.text:
            fail('Login failed.')
        else:
            save_cookie({'session': session.cookies.get('session')})
            success(f'Logged in as user [bold green]{username}[/]!')

def do_logout():
    delete_cookie()
    success('You have logged out.')

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

    account['rank'] = f'[bold green]{get_rank(fields[0])}/{fields[5]}[/]'
    account['handle'] = f'[bold {belt_hex}]{account['name']}[/]'
    if not simple and can_render_image():
        account['belt'] = download_image(f'/belt/{belt_data['color']}.svg', 'belt')
    else:
        account['belt'] = f'[bold {belt_hex}]{belt_data['color'].title()}[/]'
    account['country'] = ''.join(chr(ord(c) + ord('🇦') - ord('A')) for c in account['country'])
    account['date_ascended'] = datetime.fromisoformat(belt_data['date'])
    account['score'] = f'[bold cyan]{fields[1]}/{fields[2]}[/]'

    info(f'You are the epic hacker [bold green]{account['name']}[/]!')
    keys = ['rank', 'id', 'handle', 'belt', 'email', 'website', 'affiliation', 'country', 'bracket', 'date_ascended', 'score']
    show_table(account, 'Account Info', keys)

def show_score(username: str | None = None):
    if not username:
        me = request('/users/me')
        if me.ok:
            username = me.json().get('name')
        else:
            error(me.json().get('error', 'Unknown error'))

    score = request('/score', auth=False, params={'username': username}).json()
    fields = list(map(int, score.split(':')))

    show_table({
        'rank': f'[bold green]{get_rank(fields[0])}/{fields[5]}[/]',
        'handle': f'[bold green]{username}[/]',
        'score': f'[bold cyan]{fields[1]}/{fields[2]}[/]'
    }, 'Global ranking')

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

def show_scoreboard(dojo_id: str | None = None, module_id: str | None = None, duration: str = 'all', page: int = 1, simple: bool = False):
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
            row['handle'] = f'[bold {belt_hex}]{row['name']}[/]'
            row['badges'] = ''.join(sorted(badge['emoji'] for badge in row['badges']))

            if render_image:
                if belt not in images:
                    images[belt] = download_image(row['belt'], 'belt')
                row['belt'] = images[belt]

                if symbol not in images:
                    images[symbol] = download_image(row['symbol'])
                row['role'] = images[symbol]
            else:
                row['belt'] = f'[bold {belt_hex}]{belt.title()}[/]'
                row['role'] = 'ASU Student' if symbol == 'fork' else symbol.title()

        title = f'Scoreboard for [bold]{f'{dojo_id}/{module_id}' if module_id else dojo_id}[/]'
        show_table(standings, title, ['rank', 'role', 'handle', 'belt', 'badges', 'solves'])

    else:
        show_table(get_wechall_rankings(page, simple), 'WeChall rankings')

def show_belts(belt: str | None = None, page: int | None = None, simple: bool = False):
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
        title = f'[bold {belt_hex}]Belted Hackers[/]'
        for rank, id in enumerate(response['ranks'][belt]):
            user = response['users'][str(id)]
            user['rank'] = f'[bold green]{get_rank(rank + 1)}/{len(response['ranks'][belt])}[/]'
            user['id'] = id
            user['handle'] = f'[bold {belt_hex}]{user['handle']}[/]'
            if render_image:
                user['belt'] = images[belt]
            else:
                user['belt'] = f'[bold {belt_hex}]{user['color'].title()}[/]'
            user['website'] = user['site']
            user['date_ascended'] = user['date']
            user['date_ascended'] = datetime.fromisoformat(user['date'])
            belts.append(user)
    else:
        title = '[bold]Belted Hackers[/]'
        for rank, (id, user) in enumerate(response['users'].items()):
            belt_hex = get_belt_hex(user['color'])
            user['rank'] = f'[bold green]{get_rank(rank + 1)}/{len(response['users'])}[/]'
            user['id'] = int(id)
            user['handle'] = f'[bold {belt_hex}]{user['handle']}[/]'
            if render_image:
                user['belt'] = images[user['color']]
            else:
                user['belt'] = f'[bold {belt_hex}]{user['color'].title()}[/]'
            user['website'] = user['site']
            user['date_ascended'] = datetime.fromisoformat(user['date'])
            belts.append(user)

    if page is not None:
        belts = belts[page * 20:][:20]
    show_table(belts, title, ['rank', 'id', 'handle', 'belt', 'website', 'date_ascended'])
