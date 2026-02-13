"""
This is the main command line interface file.
"""

# TODO: transfer command implementations to utils, create more Python files if needed
# TODO: add commands for solve stats
# TODO: resolve dict.get(key) vs dict[key]
# Caveat: this CLI is designed for Linux remote challenges, might work for Mac challenges idk

import datetime
from getpass import getpass
from pathlib import Path
from requests import Session
from rich.markdown import Markdown
import shlex
from typer import Argument, Option, Typer
from typing import Annotated

from .challenge import init_challenge, show_hint, stop_challenge, submit_flag
from .config import DEFAULT_CONFIG_PATH, load_user_config, show_config
from .http import delete_cookie, request, save_cookie
from .log import error, fail, info, success, warn
from .remote import download_file, print_file, run_cmd, ssh_keygen, upload_file
from .sensai import init_sensai
from .terminal import apply_style
from .tui import init_tui
from .utils import can_render_image, download_image, get_belt_hex, get_rank, get_wechall_rankings, show_table

from .zed import init_zed

app = Typer(
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
    help=f"""
    [bold cyan]dojo[/] is a Python command line interface to interact with the website and API at {apply_style(load_user_config()['base_url'])}.

    Type -h or --help after [bold cyan]dojo[/] <COMMAND> to display further documentation for one of the below commands.

    Set the [bold green]DOJO_CONFIG[/] environment variable to override the default configuration path at {apply_style(DEFAULT_CONFIG_PATH)}.
    """,
    add_completion=False
)

@app.command(rich_help_panel='Account')
def login(
    username: Annotated[str | None, Option('-u', '--username', help='Username or email')] = None,
    password: Annotated[str | None, Option('-p', '--password', help='Password')] = None
):
    """Log into your pwn.college account and save session cookie to the cache."""

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

@app.command(rich_help_panel='Account')
def logout():
    """Log out of your pwn.college account by deleting session cookie from the cache."""

    delete_cookie()
    success('You have logged out.')

# TODO: Add change settings command
# TODO: Add standalone add ssh key command

@app.command(rich_help_panel='Account')
def keygen():
    """Generate an SSH key for the dojo and add it to user settings."""

    ssh_keygen()

@app.command('profile', help='An alias for [bold cyan]whoami[/].', rich_help_panel='User Info')
@app.command('me', help='An alias for [bold cyan]whoami[/].', rich_help_panel='User Info')
@app.command(rich_help_panel='User Info')
def whoami(
    simple: Annotated[bool, Option('-s', '--simple', help='Disable images')] = False
):
    """Show information about the current user (you!)"""

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
    account['date_ascended'] = datetime.datetime.fromisoformat(belt_data['date'])
    account['score'] = f'[bold cyan]{fields[1]}/{fields[2]}[/]'

    info(f'You are the epic hacker [bold green]{account['name']}[/]!')
    keys = ['rank', 'id', 'handle', 'belt', 'email', 'website', 'affiliation', 'country', 'bracket', 'date_ascended', 'score']
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
    dojo_id: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module_id: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    duration: Annotated[str, Option('-t', '--duration', help='Scoreboard duration (week, month, all)')] = 'all',
    page: Annotated[int, Option('-p', '--page', help='Scoreboard page')] = 1,
    simple: Annotated[bool, Option('-s', '--simple', help='Disable images')] = False
):
    """Show scoreboard for a dojo or module. If no dojo is given, show WeChall global scoreboard."""

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
            user['date_ascended'] = datetime.datetime.fromisoformat(user['date'])
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
            user['date_ascended'] = datetime.datetime.fromisoformat(user['date'])
            belts.append(user)

    if page is not None:
        belts = belts[page * 20:][:20]
    show_table(belts, title, ['rank', 'id', 'handle', 'belt', 'website', 'date_ascended'])

# TODO: add belts/emojis, solve state, personal and global solve counts
@app.command(help='An alias for [bold cyan]list[/].', rich_help_panel='Challenge Info')
@app.command('list', rich_help_panel='Challenge Info')
def ls(
    dojo_id: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module_id: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge_id: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None,
    official: Annotated[bool, Option('-o', '--official', help='Filter to official dojos')] = False,
    simple: Annotated[bool, Option('-s', '--simple', help='Disable images')] = False
):
    """List the members of a dojo or module. If no dojo is given, display all dojos."""

    if not dojo_id:
        dojos = request('/dojos', auth=False).json().get('dojos')
        if official:
            dojos = filter(lambda dojo: dojo['official'], dojos)
        # TODO: sort dojos
        render_image = not simple and can_render_image()
        table_data = []
        table_title = 'List of Dojos'
        table_keys = ['id', 'award', 'name', 'description', 'modules', 'challenges']

        for dojo_id in dojos:
            if not dojo_id['award']:
                award = None
            elif 'belt' in dojo_id['award']:
                if render_image:
                    award = download_image(f'/belt/{dojo_id['award']['belt']}.svg', 'belt')
                else:
                    belt_hex = get_belt_hex(dojo_id['award']['belt'])
                    award = f'[bold {belt_hex}]{dojo_id['award']['belt'].title()} Belt[/]'
            elif 'emoji' in dojo_id['award']:
                award = dojo_id['award']['emoji']

            table_data.append({
                'id': f'[bold cyan]{dojo_id['id']}[/]',
                'award': award,
                'name': f'[bold green]{dojo_id['name']}[/]',
                'description': Markdown(dojo_id['description']) if dojo_id['description'] else None,
                'modules': dojo_id['modules_count'],
                'challenges': dojo_id['challenges_count']
            })
    elif not module_id:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        table_data = []
        table_title = f'List of Modules in {dojo_id}'
        table_keys = ['id', 'name', 'description']

        for module_id in modules:
            table_data.append({
                'id': f'[bold cyan]{module_id['id']}[/]',
                'name': f'[bold green]{module_id['name']}[/]',
                'description': Markdown(module_id['description']) if module_id['description'] else None
            })
    elif not challenge_id:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        module = next(filter(lambda module: module['id'] == module_id, modules))
        resources = list(filter(lambda resource: resource['type'] != 'header', module['resources']))

        if resources:
            resource_title = f'List of Resources in {dojo_id}/{module_id}'
            resource_keys = ['name', 'type', 'content']

            for resource in resources:
                resource['id'] = f'[bold cyan]{resource['id']}[/]'
                resource['name'] = f'[bold green]{resource['name']}[/]'
                if resource['type'] == 'lecture':
                    resource['content'] = ''
                    if 'video' in resource:
                        youtube_url = f'https://www.youtube.com/watch?v={resource['video']}'
                        if 'playlist' in resource:
                            youtube_url += f'&list={resource['playlist']}'
                        resource['content'] += f'Video: [blue link={youtube_url}]{youtube_url}[/]\n'
                    if 'slides' in resource:
                        slides_url = f'https://docs.google.com/presentation/d/{resource['slides']}/embed'
                        resource['content'] += f'Slides: [blue link={slides_url}]{slides_url}[/]\n'
                    resource['content'] = resource['content'].strip()
                if resource['type'] == 'markdown':
                    resource['content'] = Markdown(resource['content'])
                resource['type'] = resource['type'].title()
            show_table(resources, resource_title, resource_keys, show_lines=True)

        table_data = []
        table_title = f'List of Challenges in {dojo_id}/{module_id}'
        table_keys = ['id', 'name', 'description']

        for challenge_id in module['challenges']:
            table_data.append({
                'id': f'[bold cyan]{challenge_id['id']}[/]',
                'name': f'[bold green]{challenge_id['name']}[/]',
                'description': Markdown(challenge_id['description']) if challenge_id['description'] else None
            })
    else:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        challenges = next(filter(lambda module: module['id'] == module_id, modules)).get('challenges')
        table_data = next(filter(lambda challenge: challenge['id'] == challenge_id, challenges))
        table_title = f'Challenge Info for {dojo_id}/{module_id}/{challenge_id}'
        table_keys = ['id', 'name', 'description']

        table_data['id'] = f'[bold cyan]{table_data['id']}[/]'
        table_data['name'] = f'[bold green]{table_data['name']}[/]'
        table_data['description'] = Markdown(table_data['description']) if table_data['description'] else None

    show_table(table_data, table_title, table_keys, show_lines=True)

# @app.command(rich_help_panel='Challenge Info')
def tree(
    dojo_id: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module_id: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge_id: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None
):
    """Display the children of a dojo or module in a tree. If no dojo is given, display a tree of all dojos."""

    # TODO: Implement tree mode
    # TODO: Implement TUI?

@app.command(short_help='Start a new challenge.', rich_help_panel='Challenge Launch')
def start(
    dojo_id: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module_id: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge_id: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None,
    normal: Annotated[bool, Option('-n', '--normal', help='Start in normal mode')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Start in privileged mode')] = False
):
    """
    Start a new challenge. The challenge ID can either be by itself or in the format <dojo>/<module>/<challenge>.

    If no dojo or no module is given, they are inferred from the challenge ID.
    If no challenge is given, restart the current challenge.

    If both --normal and --privileged are given, --privileged takes precedence.
    If neither --normal nor --privileged are given, start in the current mode if a challenge is running, otherwise start in normal mode.
    """

    init_challenge(dojo_id, module_id, challenge_id, normal, privileged)

@app.command('next', rich_help_panel='Challenge Launch')
def start_next(
    normal: Annotated[bool, Option('-n', '--normal', help='Start in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Start in privileged mode.')] = False
):
    """Start the next challenge in the current module."""

    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_next = active_module.json().get('c_next')
    if c_next:
        init_challenge(c_next['dojo_reference_id'], c_next['module_id'], c_next['challenge_reference_id'], normal, privileged)
    else:
        warn('This is the last challenge in the module.')

@app.command('prev', help='An alias for [bold cyan]previous[/].', rich_help_panel='Challenge Launch')
@app.command(rich_help_panel='Challenge Launch')
def previous(
    normal: Annotated[bool, Option('-n', '--normal', help='Start in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Start in privileged mode.')] = False
):
    """Start the previous challenge in the current module."""

    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_previous = active_module.json().get('c_previous')
    if c_previous:
        init_challenge(c_previous['dojo_reference_id'], c_previous['module_id'], c_previous['challenge_reference_id'], normal, privileged)
    else:
        warn('This is the first challenge in the module.')

@app.command(rich_help_panel='Challenge Launch')
def restart(
    normal: Annotated[bool, Option('-n', '--normal', help='Restart in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Restart in privileged mode.')] = False
):
    """Restart the current challenge. This will restart in the current mode by default."""

    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    init_challenge(normal=normal, privileged=privileged)

# maybe implement a backend option so it works in normal mode
@app.command(rich_help_panel='Challenge Launch')
def stop():
    """Stop the current challenge. Only works in privileged mode for now."""

    stop_challenge()

@app.command('ps', help='An alias for [bold cyan]status[/].', rich_help_panel='Challenge Status')
@app.command(rich_help_panel='Challenge Status')
def status():
    """Show the status of the current challenge."""

    response = request('/docker').json()
    if response.get('success'):
        response.pop('success')
        show_table(response, 'Challenge Status')
    else:
        fail(response.get('error'))

@app.command(rich_help_panel='Remote Connection')
def connect():
    """Connect to the current challenge via an interactive remote shell (bash by default)."""

    run_cmd()

@app.command(rich_help_panel='Remote Connection')
def fish():
    """Connect to the current challenge via fish."""

    run_cmd('fish -l')

@app.command(rich_help_panel='Remote Connection')
def nu(
    commands: Annotated[str | None, Option('-c', '--commands', help='Run the given commands and then exit.')] = None,
    execute_commands: Annotated[str | None, Option('-e', '--execute', help='Run the given commands and then enter an interactive shell.')] = None,
):
    """Connect to the current challenge via nushell."""

    nu_argv = ['nu', '-l']
    if commands is not None:
        nu_argv += ['-c', commands]
    if execute_commands is not None:
        nu_argv += ['-e', execute_commands]
    run_cmd(shlex.join(nu_argv))

@app.command(rich_help_panel='Remote Connection')
def tmux():
    """Connect to the current challenge via tmux."""

    run_cmd('tmux -l')

@app.command(rich_help_panel='Remote Connection')
def zellij():
    """Connect to the current challenge via zellij."""

    run_cmd('zellij')

@app.command(rich_help_panel='Remote Connection')
def zsh():
    """Connect to the current challenge via zsh."""

    run_cmd('zsh -l')

@app.command('ssh', help='An alias for [bold cyan]exec[/].', rich_help_panel='Remote Execution')
@app.command(help='An alias for [bold cyan]exec[/].', rich_help_panel='Remote Execution')
@app.command('exec', rich_help_panel='Remote Execution')
def run(
    command: Annotated[str | None, Argument(help='The command to run')] = None
):
    """Execute a remote command. If no command is given, start a shell like [bold cyan]connect[/]."""

    run_cmd(command)

@app.command(rich_help_panel='Remote Execution')
def du(
    path: Annotated[Path | None, Option('-p', '--path', help='Path to list files from.')] = None,
    count: Annotated[int, Option('-n', '--lines', help='Number of files to display.')] = 20
):
    """List the largest files in a directory, using [bold cyan]du[/]. Helpful when clearing up space."""

    run_cmd(f'find {path or '~'} -type f -exec du -hs {{}} + 2>/dev/null | sort -hr | head -n {count}')

@app.command(rich_help_panel='Remote Execution')
def dust(
    path: Annotated[Path | None, Option('-p', '--path', help='Path to list files from.')] = None,
    count: Annotated[int, Option('-n', '--lines', help='Number of files to display.')] = 20
):
    """List the largest files in a directory, using [bold cyan]dust[/]. Helpful when clearing up space."""

    run_cmd(f'dust -CFprsx -n {count} {path or '~'} 2>/dev/null')

@app.command(rich_help_panel='Remote Transfer')
def cat(
    path: Annotated[Path, Argument(help='The file to print')]
):
    """Print the contents of a remote file to standard out."""

    print_file(path)

@app.command('down', help='An alias for [bold cyan]download[/].', rich_help_panel='Remote Transfer')
@app.command(rich_help_panel='Remote Transfer')
def download(
    remote_path: Annotated[Path, Argument(help='Path of remote file.')],
    local_path: Annotated[Path | None, Argument(help='Path of local directory or file.')] = None
):
    """
    Download a file from remote to local.
    By default, it downloads the file to the current working directory.
    """

    download_file(remote_path, local_path)

@app.command('up', help='An alias for [bold cyan]upload[/].', rich_help_panel='Remote Transfer')
@app.command(rich_help_panel='Remote Transfer')
def upload(
    local_path: Annotated[Path, Argument(help='Path of local file.')],
    remote_path: Annotated[Path | None, Argument(help='Path of remote directory or file.')] = None,
):
    """
    Upload a file from local to remote.
    By default, it uploads the file to the configured SSH project path.
    """

    upload_file(local_path, remote_path)

@app.command(rich_help_panel='Remote Coding')
def zed(
    upgrade_zed: Annotated[bool, Option('-u', '--upgrade', help='Upgrade Zed to the latest version.')] = False,
    use_lang_servers: Annotated[bool, Option('-l', '--lsp', help='Use ruff (linter) and ty (type checker) from astral.sh, upgrade if necessary.')] = False
):
    """Open Zed, a minimal code editor written in Rust, and connect remotely to the current challenge."""

    init_zed(upgrade_zed, use_lang_servers)

@app.command(short_help="Show a hint for a challenge's flag.", rich_help_panel='Flag Submission')
def hint(
    dojo_id: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module_id: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge_id: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None
):
    """
    Show a hint for a challenge's flag.
    If no dojo or no module is given, they are inferred from the challenge ID.

    If no challenge is given, the hint will be provided for the current challenge's flag.
    """

    show_hint(dojo_id, module_id, challenge_id)

@app.command('submit', help='An alias for [bold cyan]solve[/].', rich_help_panel='Flag Submission')
@app.command(short_help='Submit a flag for a challenge.', rich_help_panel='Flag Submission')
def solve(
    flag: Annotated[str | None, Option('-f', '--flag', help='Flag to submit.')] = None,
    dojo_id: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module_id: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    challenge_id: Annotated[str | None, Option('-c', '--challenge', help='Challenge ID')] = None,
):
    """
    Submit a flag for a challenge. Warns if flag is for wrong user or challenge.

    If no dojo or no module is given, they are inferred from the challenge ID.
    If no challenge is given, the flag will be submitted for the current challenge.
    """

    submit_flag(flag, dojo_id, module_id, challenge_id)

@app.command(rich_help_panel='Configuration')
def config(
    show_default: Annotated[bool, Option('-d', '--default', help='Show the default configuration instead.')] = False
):
    """Show the current configuration settings."""

    show_config(show_default)

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
