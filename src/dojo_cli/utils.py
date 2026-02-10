"""
Utility functions for the pwn.college dojo CLI.
"""

from bs4 import BeautifulSoup
from cairosvg import svg2png
from io import BytesIO
from itsdangerous import URLSafeSerializer, URLSafeTimedSerializer
import json
from paramiko import AutoAddPolicy, SSHClient
from pathlib import Path
import re
from requests import Session
from rich import box, print as rprint
from rich.table import Column, Table
from rich.text import Text
from scp import SCPClient
from shutil import which
import subprocess
from typing import Any

from .config import load_user_config
from .constants import DOJO_AUTH_TOKEN, FLAG_PATH, TERM, TERM_PROGRAM
from .log import error, info, success, warn

if TERM_PROGRAM not in ['Apple_Terminal']:
    from textual_image.renderable import Image, SixelImage, TGPImage

def stylize_object(obj):
    object_styles = load_user_config()['object_styles']

    if isinstance(obj, str):
        if obj.startswith('http://') or obj.startswith('https://'):
            style = f'{object_styles['link']} link={obj}'
        else:
            return obj

    else:
        type_name = type(obj).__name__
        if str(obj) in object_styles:
            style = object_styles[str(obj)]
        elif type_name in object_styles:
            style = object_styles[type_name]
        else:
            return obj

    return f'[{style}]{obj}[/]'

def get_rank(num):
    rank_style = load_user_config()['object_styles']['rank']
    return '🥇🥈🥉'[num - 1] if num < 4 else f'[{rank_style}]{num}[/]'

def delete_cookie():
    cookie_path = Path(load_user_config()['cookie_path']).expanduser()
    if not cookie_path.is_file():
        error('You are not logged in.')
    cookie_path.unlink()

def load_cookie(cookie_path: Path) -> dict | None:
    assert cookie_path.is_file()
    try:
        cookie_jar = json.loads(cookie_path.read_text())
    except json.JSONDecodeError:
        error('Could not decode cookie JSON')
    if isinstance(cookie_jar, dict):
        session_cookie = cookie_jar.get('session')
        if isinstance(session_cookie, str) and len(session_cookie) > 0:
            return cookie_jar
        else:
            error('Cookie JSON does not have a valid session cookie.')
    else:
        error('Cookie JSON is not a dictionary.')

def save_cookie(cookie_jar: dict):
    cookie_path = Path(load_user_config()['cookie_path']).expanduser()
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(json.dumps(cookie_jar))

def request(url: str, api: bool = True, auth: bool = True, **kwargs):
    user_config = load_user_config()
    session = kwargs.pop('session', Session())
    method = 'POST' if 'data' in kwargs or 'json' in kwargs else 'GET'
    base_url = user_config['base_url']
    headers = kwargs.pop('headers', {})

    if not (url.startswith('http://') or url.startswith('https://')):
        url = base_url + (user_config['api'] if api else '') + url

    if auth:
        cookie_path = Path(user_config['cookie_path']).expanduser()
        if cookie_path.is_file():
            cookie_jar = load_cookie(cookie_path)
            if cookie_jar:
                headers['Cookie'] = f'session={cookie_jar['session']}'
                if session.get(base_url + '/settings', headers=headers, allow_redirects=False).is_redirect:
                    error('Session expired, please login again.')
            else:
                error('Something went wrong loading the cookie jar.')
        elif is_remote() and deserialize_auth_token(DOJO_AUTH_TOKEN):
            headers['Authorization'] = f'Bearer {DOJO_AUTH_TOKEN}'
        else:
            error('Request is not authorized, please login or run this in the dojo.')

    try:
        return session.request(method, url, headers=headers, **kwargs)
    except Exception as e:
        error(f'Request failed: {e}')

def get_wechall_rankings(page: int = 1, simple: bool = False):
    render_image = not simple and can_render_image()
    wechall_html = request(f'https://www.wechall.net/site/ranking/for/104/pwn_college/page-{page}')
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

def check_challenge_session() -> bool:
    return request('/docker').json().get('success')

def is_remote() -> bool:
    return DOJO_AUTH_TOKEN.startswith('sk-workspace-local-')

def parse_challenge_path(challenge: str, challenge_data: dict = {}) -> list:
    if re.fullmatch(r'[\-\w]+', challenge):
        if not challenge_data:
            challenge_data = request('/docker').json()
        if challenge_data.get('success'):
            return [challenge_data.get('dojo'), challenge_data.get('module'), challenge]
        return []

    return re.findall(r'/([\-~\w]+)/([\-\w]+)/([\-\w]+)', challenge)

def ssh_keygen():
    if is_remote():
        error('Please run this locally instead of on the dojo.')

    if not Path(which('ssh-keygen') or '/usr/bin/ssh-keygen').is_file():
        error('Please install ssh-keygen first.')

    user_config = load_user_config()
    ssh_config = user_config['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

    if ssh_identity_file.is_file():
        warn(f'Identity file already exists at {ssh_identity_file}, override?')
        choice = input('(y/N) > ')
        if choice.strip()[0].lower() != 'y':
            warn('Aborting SSH key generation!')
            return

    subprocess.run(['ssh-keygen', '-N', '', '-f', ssh_identity_file, '-t', ssh_config['algorithm']])

    if not ssh_config_file.is_file():
        ssh_config_file.touch(0o644)

    ssh_config_data = ssh_config_file.read_text()
    if f'Host {ssh_config['Host']}' not in ssh_config_data:
        if ssh_config_data:
            ssh_config_data += '\n'
        ssh_config_data += f'Host {ssh_config['Host']}\n'
        ssh_config_data += f'  HostName {ssh_config['HostName']}\n'
        ssh_config_data += f'  Port {ssh_config['Port']}\n'
        ssh_config_data += f'  User {ssh_config['User']}\n'
        ssh_config_data += f'  IdentityFile {ssh_identity_file}\n'
        ssh_config_data += f'  ServerAliveCountMax {ssh_config['ServerAliveCountMax']}\n'
        ssh_config_data += f'  ServerAliveInterval {ssh_config['ServerAliveInterval']}\n'
        ssh_config_file.write_text(ssh_config_data)

    public_key = (ssh_identity_file.parent / (ssh_identity_file.name + '.pub')).read_text()
    if Path(user_config['cookie_path']).expanduser().is_file():
        response = request('/ssh_key', json={'ssh_key': public_key}).json()
        if response['success']:
            success('Successfully added public key to settings. You can now start a challenge and connect to the remote server.')
        else:
            error(f'Something went wrong: {response['error']}')
    else:
        ssh_key_url = f'{user_config['base_url']}/settings#ssh-key'
        info(f'Public key: [bold cyan]{public_key}[/]')
        info('Not logged in, could not automatically add the public key to your pwn.college account.')
        info(f'Log into pwn.college using a browser and navigate to [cyan link={ssh_key_url}]{ssh_key_url}[/].')
        info('Enter the above key into the [bold cyan]Add New SSH Key[/] field, and click [bold cyan]Add[/].')

def run_cmd(command: str | None = None, capture_output: bool = False, payload: bytes | None = None, mode: str = 'openssh') -> bytes | None:
    """Run a command on the remote server. If capture_output is True, the stdout bytes are returned."""

    if mode == 'local' or is_remote():
        return subprocess.run(command or 'bash', shell=True, capture_output=capture_output, input=payload).stdout

    if not check_challenge_session():
        error('No active challenge session; start a challenge!')

    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

    if mode == 'paramiko':
        with SSHClient() as client:
            client.load_system_host_keys()
            client.set_missing_host_key_policy(AutoAddPolicy())
            client.connect(
                ssh_config['HostName'],
                ssh_config['Port'],
                ssh_config['User'],
                key_filename=str(ssh_identity_file)
            )
            if command:
                stdin, stdout, _ = client.exec_command(command)
                if payload:
                    stdin.write(payload)
                    stdin.channel.shutdown_write()
                while not stdout.channel.exit_status_ready():
                    pass
                if capture_output:
                    return stdout.read()
            else:
                # This is a really basic shell that I ripped off YouTube
                # idk how to get invoke_shell to feel like a real shell
                while True:
                    try:
                        command = input('$ ')
                        if command == 'exit':
                            break
                        stdin, stdout, _ = client.exec_command(command)
                        print(stdout.read().decode(), end='')
                    except KeyboardInterrupt:
                        break

    elif mode == 'openssh':
        if not which('ssh'):
            error('Please install ssh first.')

        if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
            ssh_argv = ['ssh', '-F', ssh_config_file, ssh_config['Host']]
        elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
            ssh_argv = [
                'ssh', '-i', ssh_identity_file,
                '-o', f'ServerAliveCountMax={ssh_config['ServerAliveCountMax']}',
                '-o', f'ServerAliveInterval={ssh_config['ServerAliveInterval']}',
                f'{ssh_config['User']}@{ssh_config['HostName']}:{ssh_config['Port']}'
            ]
        else:
            error('Something went wrong with ssh config or the ssh identity file, please make sure at least one is valid.')

        if command:
            ssh_argv.extend(['-t', command])

        return subprocess.run(ssh_argv, capture_output=capture_output, input=payload).stdout

    else:
        error('Unsupported remote connection mode.')

def transfer(src_path: Path | str, dst_path: Path | str, upload: bool = False, mode: str = 'paramiko'):
    if is_remote():
        error('Please run this locally instead of on the dojo.')
    if not check_challenge_session():
        error('No active challenge session; start a challenge!')

    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

    if mode == 'paramiko':
        with SSHClient() as ssh_client:
            ssh_client.load_system_host_keys()
            ssh_client.set_missing_host_key_policy(AutoAddPolicy())
            ssh_client.connect(
                ssh_config['HostName'],
                ssh_config['Port'],
                ssh_config['User'],
                key_filename=str(ssh_identity_file)
            )
            with SCPClient(ssh_client.get_transport()) as scp_client:
                getattr(scp_client, 'put' if upload else 'get')(src_path, dst_path)

    elif mode == 'scp':
        scp_client = Path(which('scp') or '/usr/bin/scp')
        if not scp_client.is_file():
            error('Please install scp and ensure its parent directory is in PATH.')

        if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
            scp_argv = [
                scp_client, '-F', ssh_config_file,
                src_path if upload else f'{ssh_config['Host']}:{src_path}',
                f'{ssh_config['Host']}:{dst_path}' if upload else dst_path
            ]
        elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
            scp_argv = [
                scp_client, '-i', ssh_identity_file,
                src_path if upload else f'scp://{ssh_config['User']}@{ssh_config['HostName']}:{ssh_config['Port']}/{src_path}',
                f'scp://{ssh_config['User']}@{ssh_config['HostName']}:{ssh_config['Port']}/{dst_path}' if upload else dst_path
            ]
        else:
            error('Something went wrong with ssh config or the ssh identity file, please make sure at least one is valid.')

        subprocess.run(scp_argv)

    elif mode == 'cat':
        if upload:
            run_cmd(f'cat > {dst_path}', payload=Path(src_path).expanduser().read_bytes())
        else:
            file_data = run_cmd(f'cat {src_path}', True)
            if file_data is not None:
                Path(dst_path).expanduser().write_bytes(file_data)

    else:
        error('Unsupported transfer mode.')

def get_flag_size() -> int:
    if is_remote():
        if FLAG_PATH.is_file():
            return FLAG_PATH.stat().st_size
        else:
            error('Flag file does not exist.')

    elif check_challenge_session():
        stat_query = run_cmd('stat -c %s /flag', True)
        if stat_query and stat_query.strip().isdigit():
            return int(stat_query)
        error('Flag size query failed.')

    else:
        error('No active challenge session; start a challenge!')

    return 0

def serialize_flag(account_id: int, challenge_id: int) -> str:
    return URLSafeSerializer('').dumps([account_id, challenge_id])[::-1]

def deserialize_flag(flag: str) -> list[int] | None:
    return URLSafeSerializer('').loads_unsafe(re.sub('.+?{(.+)}', r'\1', flag)[::-1])[1]

def deserialize_auth_token(auth_token: str) -> list | None:
    token_prefix = 'sk-workspace-local-'
    if auth_token.startswith(token_prefix):
        token_data = URLSafeTimedSerializer('').loads_unsafe(auth_token[len(token_prefix):])[1]
        if isinstance(token_data, list) and len(token_data) == 3:
            if isinstance(token_data[0], int) and isinstance(token_data[1], str) and isinstance(token_data[2], str):
                return token_data
    return None

def get_box(s: str) -> box.Box | None:
    if hasattr(box, s) and isinstance(getattr(box, s), box.Box):
        return getattr(box, s)
    lines = s.splitlines()
    if len(lines) == 8 and all(len(line) == 4 for line in lines):
        return box.Box(s)

def display_table(table_data: dict[str, Any] | list[dict[str, Any]], title: str | None = None, keys: list[str] | None = None):
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
    [table.add_row(*[stylize_object(row[key]) for key in keys]) for row in table_data]
    rprint(table)

def get_belt_color(belt: str) -> str:
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
