"""
This is the main command line interface file.
"""

# TODO: transfer command implementations to utils, create more Python files if needed
# TODO: add commands for solve stats
# TODO: replace remote command queries with SFTP equivalents
# Caveat: this CLI is designed for Linux remote challenges, might work for Mac challenges idk

from getpass import getpass
from pathlib import Path
import re
from requests import Session
from rich.markdown import Markdown
from typer import Argument, Option, Typer
from typing import Annotated

from .config import DEFAULT_CONFIG_PATH, display_config, load_user_config
from .log import error, fail, info, success, warn
from .sensai import init_sensai
from .tui import init_tui
from .utils import (
    delete_cookie, save_cookie,
    request, get_wechall_rankings,
    check_challenge_session, parse_challenge_path,
    is_remote, run_cmd, transfer, ssh_keygen,
    show_table, get_rank, show_hint, submit_flag,
    get_belt_color, can_render_image, download_image
)
from .zed import init_zed

app = Typer(
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
    help=f"""
    [bold cyan]dojo[/] is a Python command line interface to interact with the pwn.college website and API.

    Type -h or --help after [bold cyan]dojo[/] <COMMAND> to display further documentation for one of the below commands.

    Set the [bold green]DOJO_CONFIG[/] environment variable to override the default configuration path at [bold yellow]{DEFAULT_CONFIG_PATH}[/].
    """,
    add_completion=False
)

@app.command(rich_help_panel='Account')
def login(
    username: Annotated[str | None, Option('-u', '--username', help='Username or email')] = None,
    password: Annotated[str | None, Option('-p', '--password', help='Password')] = None
):
    """Log into pwn.college account and save session cookie to the cache."""

    while not username:
        username = input('Enter username or email: ')
    while not password:
        password = getpass('Enter password: ', echo_char='*')

    with Session() as session:
        nonce = re.search(r''''csrfNonce': "(\w+)"''', request('', False, False, session=session).text)
        if nonce:
            login_data = {'name': username, 'password': password, 'nonce': nonce.group(1)}
            response = request('/login', False, False, session=session, data=login_data)

            if 'Your username or password is incorrect' in response.text:
                fail('Login failed.')
            else:
                save_cookie({'session': session.cookies.get('session')})
                success(f'Logged in as user [bold green]{username}[/]!')
        else:
            error('Failed to extract nonce.')

@app.command(rich_help_panel='Account')
def logout():
    """Log out of pwn.college account by deleting session cookie from the cache."""

    delete_cookie()
    success('You have logged out.')

# TODO: Add change settings command
# TODO: Add standalone add ssh key command

@app.command(rich_help_panel='Account')
def keygen():
    """Generate SSH key for the dojo and add it to the account."""

    ssh_keygen()

@app.command('profile', help='An alias for [bold cyan]whoami[/].', rich_help_panel='User Info')
@app.command('me', help='An alias for [bold cyan]whoami[/].', rich_help_panel='User Info')
@app.command(rich_help_panel='User Info')
def whoami():
    """Show information about the current user (you!)"""

    me = request('/users/me')
    account = me.json()
    if not me.ok:
        error(account.get('error', 'Unknown error'))

    score = request('/score', auth=False, params={'username': account['name']})
    fields = list(map(int, score.json().split(':')))
    account['rank'] = f'[bold green]{get_rank(fields[0])}/{fields[5]}[/]'
    account['handle'] = f'[bold green]{account['name']}[/]'
    account['score'] = f'[bold cyan]{fields[1]}/{fields[2]}[/]'

    info(f'You are the epic hacker [bold green]{account['name']}[/]!')
    keys = ['rank', 'id', 'handle', 'email', 'website', 'affiliation', 'country', 'bracket', 'score']
    show_table(account, 'Account Info', keys)

@app.command('score', help='An alias for [bold cyan]whois[/].', rich_help_panel='User Info')
@app.command('rank', help='An alias for [bold cyan]whois[/].', rich_help_panel='User Info')
@app.command(rich_help_panel='User Info')
def whois(
    username: Annotated[str | None, Option('-u', '--username', help='Username to query')] = None,
):
    """Show global ranking for another user. If no username is given, show the current user's ranking."""

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

@app.command(rich_help_panel='User Info')
def scoreboard(
    dojo: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    duration: Annotated[str, Option('-t', '--duration', help='Scoreboard duration (week, month, all)')] = 'all',
    page: Annotated[int, Option('-p', '--page', help='Scoreboard page')] = 1,
    simple: Annotated[bool, Option('-s', '--simple', help='Disable images')] = False
):
    """Show scoreboard for a dojo or module. If no dojo is given, show WeChall global scoreboard."""

    if dojo:
        durations = {'week': 7, 'month': 30, 'all': 0}
        endpoint = f'/scoreboard/{dojo}/{module or '_'}/{durations.get(duration.lower(), 0)}/{page}'
        standings = request(endpoint, auth=False).json().get('standings')
        images = {}
        render_image = not simple and can_render_image()

        for row in standings:
            belt = row['belt'].split('/')[-1].split('.')[0]
            symbol = row['symbol'].split('/')[-1].split('.')[0]
            color = get_belt_color(belt)

            row['rank'] = get_rank(row['rank'])
            row['handle'] = f'[bold {color}]{row['name']}[/]'
            row['badges'] = ''.join(sorted(badge['emoji'] for badge in row['badges']))

            if render_image:
                if belt not in images:
                    images[belt] = download_image(row['belt'], 'belt')
                row['belt'] = images[belt]

                if symbol not in images:
                    images[symbol] = download_image(row['symbol'])
                row['role'] = images[symbol]
            else:
                row['belt'] = f'[bold {color}]{belt.title()}[/]'
                row['role'] = 'ASU Student' if symbol == 'fork' else symbol.title()

        title = f'Scoreboard for [bold]{f'{dojo}/{module}' if module else dojo}[/]'
        show_table(standings, title, ['rank', 'role', 'handle', 'belt', 'badges', 'solves'])

    else:
        show_table(get_wechall_rankings(page, simple), 'WeChall rankings')

@app.command(rich_help_panel='User Info')
def belts(
    belt: Annotated[str | None, Option('-c', '--color', help='Filter by belt color')] = None,
    page: Annotated[int | None, Option('-p', '--page', help='Belt list page')] = None,
    simple: Annotated[bool, Option('-s', '--simple', help='Disable images')] = False
):
    """Show all the users who have earned belts above white belt."""
    response = request('/belts', auth=False).json()

    render_image = not simple and can_render_image()
    if render_image:
        if belt in response['ranks']:
            images = {belt: download_image(f'/belt/{belt}.svg', 'belt')}
        else:
            images = {belt: download_image(f'/belt/{belt}.svg', 'belt') for belt in response['ranks']}

    belts = []
    if belt in response['ranks']:
        color = get_belt_color(belt)
        title = f'[bold {color}]Belted Hackers[/]'
        for rank, id in enumerate(response['ranks'][belt]):
            user = response['users'][str(id)]
            user['rank'] = f'[bold green]{get_rank(rank + 1)}/{len(response['ranks'][belt])}[/]'
            user['id'] = id
            user['handle'] = f'[bold {color}]{user['handle']}[/]'
            if render_image:
                user['belt'] = images[belt]
            else:
                user['belt'] = f'[bold {color}]{user['color'].title()}[/]'
            user['website'] = user['site']
            user['date_ascended'] = user['date']
            belts.append(user)
    else:
        title = '[bold]Belted Hackers[/]'
        for rank, (id, user) in enumerate(response['users'].items()):
            color = get_belt_color(user['color'])
            user['rank'] = f'[bold green]{get_rank(rank + 1)}/{len(response['users'])}[/]'
            user['id'] = int(id)
            user['handle'] = f'[bold {color}]{user['handle']}[/]'
            if render_image:
                user['belt'] = images[user['color']]
            else:
                user['belt'] = f'[bold {color}]{user['color'].title()}[/]'
            user['website'] = user['site']
            user['date_ascended'] = user['date']
            belts.append(user)

    if page is not None:
        belts = belts[page * 20:][:20]
    show_table(belts, title, ['rank', 'id', 'handle', 'belt', 'website', 'date_ascended'])

# TODO: add solve counts for challenges
@app.command(help='An alias for [bold cyan]list[/].', rich_help_panel='Challenge Info')
@app.command('list', rich_help_panel='Challenge Info')
def ls(
    dojo: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None
):
    """List the members of a dojo or module. If no dojo is given, display all dojos."""

    if not dojo:
        dojos = request('/dojos', auth=False).json().get('dojos')
        table_data = []
        table_title = 'List of Dojos'
        for dojo in dojos:
            table_data.append({
                'id': f'[bold cyan]{dojo['id']}[/]',
                'name': f'[bold green]{dojo['name']}[/]',
                'description': Markdown(dojo['description'] or 'N/A')
            })
    elif not module:
        modules = request(f'/dojos/{dojo}/modules', auth=False).json().get('modules')
        table_data = []
        table_title = f'List of Modules in {dojo}'
        for module in modules:
            table_data.append({
                'id': f'[bold cyan]{module['id']}[/]',
                'name': f'[bold green]{module['name']}[/]',
                'description': Markdown(module['description'] or 'N/A')
            })
    elif not challenge:
        modules = request(f'/dojos/{dojo}/modules', auth=False).json().get('modules')
        challenges = next(m for m in modules if m['id'] == module).get('challenges')
        table_data = []
        table_title = f'List of Challenges in {dojo}/{module}'
        for challenge in challenges:
            table_data.append({
                'id': f'[bold cyan]{challenge['id']}[/]',
                'name': f'[bold green]{challenge['name']}[/]',
                'description': Markdown(challenge['description'] or 'N/A')
            })
    else:
        modules = request(f'/dojos/{dojo}/modules', auth=False).json().get('modules')
        challenges = next(m for m in modules if m['id'] == module).get('challenges')
        table_data = next(c for c in challenges if c['id'] == challenge)
        table_title = f'Challenge Info for {dojo}/{module}/{challenge}'
        table_data['id'] = f'[bold cyan]{table_data['id']}[/]'
        table_data['name'] = f'[bold green]{table_data['name']}[/]'
        table_data['description'] = Markdown(table_data['description'] or 'N/A')

    show_table(table_data, table_title, ['id', 'name', 'description'])

# @app.command(rich_help_panel='Challenge Info')
def tree(
    dojo: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None
):
    """Display the children of a dojo or module in a tree. If no dojo is given, display a tree of all dojos."""

    # TODO: Implement tree mode
    # TODO: Implement TUI?

@app.command(short_help='Start a new challenge.', rich_help_panel='Challenge Launch')
def start(
    dojo: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None,
    normal: Annotated[bool, Option('-n', '--normal', help='Start in normal mode')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Start in privileged mode')] = False
):
    """
    Start a new challenge. The challenge ID can either be by itself or in the format <dojo>/<module>/<challenge>.

    If no dojo or no module is given, they are inferred from the challenge ID.
    If no challenge is given, restart the current challenge.

    If neither --normal nor --privileged are given, start in the current mode if a challenge is running, otherwise start in normal mode.
    """

    if normal and privileged:
        error('Cannot start challenge in both normal and privileged mode. Please select only one.')

    chal_data = request('/docker').json()

    if not challenge:
        if chal_data['success']:
            dojo, module, challenge = chal_data['dojo'], chal_data['module'], chal_data['challenge']
        else:
            error('No active challenge session; please specify a challenge name!')
    elif not dojo or not module:
        challenge_path = parse_challenge_path(challenge, chal_data)
        if len(challenge_path) == 3 and all(isinstance(s, str) for s in challenge_path):
            # TODO: confirm this challenge actually exists
            dojo, module, challenge = challenge_path
        else:
            error('Could not parse challenge ID.')

    practice = privileged or not normal or chal_data.get('practice', False)
    request_json = {'dojo': dojo, 'module': module, 'challenge': challenge, 'practice': practice}
    response = request('/docker', csrf=True, json=request_json).json()
    if response.get('success'):
        success('Challenge started successfully!')
    elif response.get('error'):
        error(response['error'])
    else:
        error('Failed to start challenge.')

@app.command('next', rich_help_panel='Challenge Launch')
def start_next(
    normal: Annotated[bool, Option('-n', '--normal', help='Start in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Start in privileged mode.')] = False
):
    """Start next challenge in the module."""

    if not check_challenge_session():
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_next = active_module.json().get('c_next')
    if c_next:
        start(c_next['dojo_reference_id'], c_next['module_id'], c_next['challenge_reference_id'], normal, privileged)
    else:
        warn('This is the last challenge in the module.')

@app.command('prev', help='An alias for [bold cyan]previous[/].', rich_help_panel='Challenge Launch')
@app.command(rich_help_panel='Challenge Launch')
def previous(
    normal: Annotated[bool, Option('-n', '--normal', help='Start in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Start in privileged mode.')] = False
):
    """Start previous challenge in the module."""

    if not check_challenge_session():
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_previous = active_module.json().get('c_previous')
    if c_previous:
        start(c_previous['dojo_reference_id'], c_previous['module_id'], c_previous['challenge_reference_id'], normal, privileged)
    else:
        warn('This is the first challenge in the module.')

@app.command(rich_help_panel='Challenge Launch')
def restart(
    normal: Annotated[bool, Option('-n', '--normal', help='Restart in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Restart in privileged mode.')] = False
):
    """Restart the current challenge. This will restart in the current mode by default."""

    if not check_challenge_session():
        error('No active challenge session; start a challenge!')

    start(normal=normal, privileged=privileged)

# maybe implement a backend option so it works in normal mode
@app.command(rich_help_panel='Challenge Launch')
def stop():
    """Stop the current challenge. Only works in privileged mode for now."""

    response = request('/docker').json()
    if response.get('success'):
        if response.get('practice'):
            run_cmd('sudo kill 1', True)
            if not request('/docker').json().get('success'):
                success('Challenge stopped successfully!')
        else:
            error('Challenge is in normal mode, cannot stop container without root privileges.')
    else:
        error('No active challenge session; start a challenge!')

@app.command('ps', help='An alias for [bold cyan]status[/].', rich_help_panel='Challenge Status')
@app.command(rich_help_panel='Challenge Status')
def status():
    """Show the status of the current challenge."""

    response = request('/docker').json()
    if response['success']:
        response.pop('success')
        show_table(response, 'Challenge Status')
    else:
        fail(response['error'])

@app.command('ssh', help='An alias for [bold cyan]connect[/].', rich_help_panel='Remote Connection')
@app.command(rich_help_panel='Remote Connection')
def connect():
    """Connect to the current challenge via an interactive remote shell."""

    run_cmd()

@app.command(help='An alias for [bold cyan]exec[/].', rich_help_panel='Remote Connection')
@app.command('exec', rich_help_panel='Remote Connection')
def run(
    command: Annotated[str | None, Argument(help='The command to run')] = None
):
    """Execute a remote command. If no command is given, start a shell like [bold cyan]connect[/]."""

    run_cmd(command)

@app.command(rich_help_panel='Remote Connection')
def du(
    path: Annotated[Path | None, Option('-p', '--path', help='Path to list files from.')] = None,
    count: Annotated[int, Option('-n', '--lines', help='Number of files to display.')] = 20
):
    """List the largest files in a directory, using [bold cyan]du[/]. Helpful when clearing up space."""

    run_cmd(f'find {path or '~'} -type f -exec du -hs {{}} + 2>/dev/null | sort -hr | head -n {count}')

@app.command(rich_help_panel='Remote Connection')
def dust(
    path: Annotated[Path | None, Option('-p', '--path', help='Path to list files from.')] = None,
    count: Annotated[int, Option('-n', '--lines', help='Number of files to display.')] = 20
):
    """List the largest files in a directory, using [bold cyan]dust[/]. Helpful when clearing up space."""

    run_cmd(f'dust -CFprx -n {count} {path or '~'} 2>/dev/null')

@app.command('down', help='An alias for [bold cyan]download[/].', rich_help_panel='Remote Transfer')
@app.command(rich_help_panel='Remote Transfer')
def download(
    remote_path: Annotated[Path, Argument(help='Path of remote file.')],
    local_path: Annotated[Path | None, Argument(help='Path of local directory or file.')] = None
):
    """Download a file from remote to local. By default, it downloads the file to the current working directory."""

    if is_remote():
        error('Please run this locally instead of on the dojo.')

    file_query = run_cmd(f'file {remote_path}', True)
    if file_query:
        if b'(No such file or directory)' in file_query or file_query.split()[-1] == b'directory':
            error('Remote path is not a file.')
    else:
        error('Could not query file.')

    if not local_path:
        local_path = Path.cwd()

    local_path = local_path.expanduser()

    if local_path.is_dir():
        local_path /= remote_path.name

    transfer(str(remote_path), str(local_path))
    success(f'Downloaded {remote_path} to {local_path}')

@app.command('up', help='An alias for [bold cyan]upload[/].', rich_help_panel='Remote Transfer')
@app.command(rich_help_panel='Remote Transfer')
def upload(
    local_path: Annotated[Path, Argument(help='Path of local file.')],
    remote_path: Annotated[Path | None, Argument(help='Path of remote directory or file.')] = None,
):
    """Upload a file from local to remote. By default, it uploads the file to [bold yellow]/home/hacker[/]."""

    if is_remote():
        error('Please run this locally instead of on the dojo.')

    local_path = local_path.expanduser()

    if not local_path.is_file():
        error('Provided path is not a file.')

    if remote_path is None:
        remote_path = Path(load_user_config()['ssh']['project_path'])

    file_query = run_cmd(f'file {remote_path}', True)

    if file_query is None:
        error('Could not query file.')
    else:
        if b'(No such file or directory)' in file_query:
            run_cmd(f'mkdir -p {remote_path.parent}')
        elif file_query.split()[-1] == b'directory':
            remote_path /= local_path.name

    transfer(str(local_path), str(remote_path), True)
    success(f'Uploaded {local_path} to {remote_path}')

@app.command(rich_help_panel='Remote Connection')
def zed(
    upgrade_zed: Annotated[bool, Option('-u', '--upgrade', help='Upgrade zed to the latest version.')] = False,
    use_lang_servers: Annotated[bool, Option('-l', '--lsp', help='Use ruff and ty, upgrade if necessary.')] = False
):
    """Open the Zed code editor and connect to the current challenge."""

    init_zed(upgrade_zed, use_lang_servers)

@app.command(short_help="Show a hint for a challenge's flag.", rich_help_panel='Flag Submission')
def hint(
    dojo: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None
):
    """
    Show a hint for a challenge's flag.
    If no dojo or no module is given, they are inferred from the challenge ID.

    If no challenge is given, the hint will be provided for the current challenge's flag.
    """

    show_hint(dojo, module, challenge)

@app.command('submit', help='An alias for [bold cyan]solve[/].', rich_help_panel='Flag Submission')
@app.command(short_help='Submit a flag for a challenge.', rich_help_panel='Flag Submission')
def solve(
    flag: Annotated[str | None, Option('-f', '--flag', help='Flag to submit.')] = None,
    dojo: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None,
):
    """
    Submit a flag for a challenge. Warns if flag is for wrong user or challenge.

    If no dojo or no module is given, they are inferred from the challenge ID.
    If no challenge is given, the flag will be submitted for the current challenge.
    """

    submit_flag(flag, dojo, module, challenge)

@app.command(rich_help_panel='Configuration')
def config(
    default: Annotated[bool, Option('-d', '--default', help='Show the default configuration instead.')] = False
):
    """Show the current configuration settings."""

    display_config(default)

@app.command(rich_help_panel='Help')
def help():
    """Start a TUI to explore command documentation for the CLI. Press [bold cyan]^q[/] to quit."""

    init_tui(app)

@app.command(rich_help_panel='Help')
def sensai():
    """Communicate with the pwn.college SensAI assistant."""

    init_sensai()

@app.command(rich_help_panel='Help')
def discord():
    """Show the link to the pwn.college Discord server."""

    info('Go to [cyan]https://discord.gg/pwncollege[/] or click [cyan link=https://discord.gg/pwncollege]here[/].')
