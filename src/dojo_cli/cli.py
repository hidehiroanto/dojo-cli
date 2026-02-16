"""
This is the main command line interface file.
"""

# TODO: add commands for solve stats
# TODO: resolve dict.get(key) vs dict[key]
# Caveat: this CLI is designed for Linux remote challenges, might work for Mac challenges idk

from pathlib import Path
from typer import Argument, Option, Typer
from typing import Annotated

from .challenge import (
    init_challenge, init_next, init_previous, restart_challenge,
    show_hint, show_list, show_status, stop_challenge, submit_flag
)
from .config import DEFAULT_CONFIG_PATH, show_config
from .editor import init_editor, mount_remote
from .log import info
from .remote import bat_file, download_file, print_file, run_cmd, ssh_keygen, upload_file
from .sensai import init_sensai
from .shell import init_bash, init_fish, init_nu, init_zsh
from .terminal import apply_style
from .tui import init_tui
from .user import do_login, do_logout, show_belts, show_me, show_score, show_scoreboard
from .zed import init_zed

app = Typer(
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
    help=f"""
    [bold cyan]dojo[/] is a Python command line interface to interact with the website and API at [bold underline blue]pwn.college[/].

    Type -h or --help after [bold cyan]dojo[/] <COMMAND> to display further documentation for one of the below commands.

    Set the [bold green]DOJO_CONFIG[/] environment variable to override the default configuration path at {apply_style(DEFAULT_CONFIG_PATH)}.
    """,
    add_completion=False
)

@app.command(rich_help_panel='User Login and Settings')
def login(
    username: Annotated[str | None, Option('-u', '--username', help='Username or email')] = None,
    password: Annotated[str | None, Option('-p', '--password', help='Password')] = None
):
    """Log into your pwn.college account and save session cookie to the cache."""

    do_login(username, password)

@app.command(rich_help_panel='User Login and Settings')
def logout():
    """Log out of your pwn.college account by deleting session cookie from the cache."""

    do_logout()

# TODO: Add change settings command
# TODO: Add standalone add ssh key command

@app.command(rich_help_panel='User Login and Settings')
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

    show_me(simple)

@app.command('score', help='An alias for [bold cyan]whois[/].', rich_help_panel='User Info')
@app.command('rank', help='An alias for [bold cyan]whois[/].', rich_help_panel='User Info')
@app.command(rich_help_panel='User Info')
def whois(
    username: Annotated[str | None, Option('-u', '--username', help='Username to query')] = None,
):
    """Show global ranking for another user. If no username is given, show the current user's ranking."""

    show_score(username)

@app.command(rich_help_panel='User Info')
def scoreboard(
    dojo_id: Annotated[str | None, Option('-d', '--dojo', help='Dojo ID')] = None,
    module_id: Annotated[str | None, Option('-m', '--module', help='Module ID')] = None,
    duration: Annotated[str, Option('-t', '--duration', help='Scoreboard duration (week, month, all)')] = 'all',
    page: Annotated[int, Option('-p', '--page', help='Scoreboard page')] = 1,
    simple: Annotated[bool, Option('-s', '--simple', help='Disable images')] = False
):
    """Show scoreboard for a dojo or module. If no dojo is given, show WeChall global scoreboard."""

    show_scoreboard(dojo_id, module_id, duration, page, simple)

@app.command(rich_help_panel='User Info')
def belts(
    belt: Annotated[str | None, Option('-c', '--color', help='Filter by belt color')] = None,
    page: Annotated[int | None, Option('-p', '--page', help='Belt list page')] = None,
    simple: Annotated[bool, Option('-s', '--simple', help='Disable images')] = False
):
    """Show all the users who have earned belts above white belt."""

    show_belts(belt, page, simple)

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

    show_list(dojo_id, module_id, challenge_id, official, simple)

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

    init_next(normal, privileged)

@app.command('prev', help='An alias for [bold cyan]previous[/].', rich_help_panel='Challenge Launch')
@app.command(rich_help_panel='Challenge Launch')
def previous(
    normal: Annotated[bool, Option('-n', '--normal', help='Start in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Start in privileged mode.')] = False
):
    """Start the previous challenge in the current module."""

    init_previous(normal, privileged)

@app.command(rich_help_panel='Challenge Launch')
def restart(
    normal: Annotated[bool, Option('-n', '--normal', help='Restart in normal mode.')] = False,
    privileged: Annotated[bool, Option('-p', '--practice', '--privileged', help='Restart in privileged mode.')] = False
):
    """Restart the current challenge. This will restart in the current mode by default."""

    restart_challenge(normal, privileged)

# maybe implement a backend option so it works in normal mode
@app.command(rich_help_panel='Challenge Launch')
def stop():
    """Stop the current challenge. Only works in privileged mode for now."""

    stop_challenge()

@app.command('ps', help='An alias for [bold cyan]status[/].', rich_help_panel='Challenge Status')
@app.command(rich_help_panel='Challenge Status')
def status():
    """Show the status of the current challenge."""

    show_status()

@app.command(rich_help_panel='Remote Connection')
def connect():
    """Connect to the current challenge via an interactive remote shell (bash by default)."""

    run_cmd()

@app.command(rich_help_panel='Remote Connection')
def bash(
    command_string: Annotated[str | None, Option('-c', help='Run the given command and then exit.')] = None
):
    """Connect to the current challenge via a bash login shell."""

    init_bash(command_string)

@app.command(rich_help_panel='Remote Connection')
def fish(
    command: Annotated[str | None, Option('-c', '--command', help='Run the given command and then exit.')] = None,
    init_command: Annotated[str | None, Option('-C', '--init-command', help='Run the given command and then enter an interactive shell.')] = None
):
    """Connect to the current challenge via a fish login shell."""

    init_fish(command, init_command)

@app.command(rich_help_panel='Remote Connection')
def nu(
    commands: Annotated[str | None, Option('-c', '--commands', help='Run the given commands and then exit.')] = None,
    exec_commands: Annotated[str | None, Option('-e', '--execute', help='Run the given commands and then enter an interactive shell.')] = None
):
    """Connect to the current challenge via a nushell login shell."""

    init_nu(commands, exec_commands)

@app.command(rich_help_panel='Remote Connection')
def tmux():
    """Connect to the current challenge via a tmux login shell."""

    run_cmd('tmux -l')

@app.command(rich_help_panel='Remote Connection')
def zellij():
    """Connect to the current challenge via zellij."""

    run_cmd('zellij')

@app.command(rich_help_panel='Remote Connection')
def zsh(
    command: Annotated[str | None, Option('-c', help='Run the given command and then exit.')] = None
):
    """Connect to the current challenge via a zsh login shell."""

    init_zsh(command)

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
def bat(
    path: Annotated[Path, Argument(help='The file to print')]
):
    """Print the contents of a remote file to standard out using [bold cyan]bat[/]."""

    bat_file(path)

@app.command(rich_help_panel='Remote Transfer')
def cat(
    path: Annotated[Path, Argument(help='The file to print')]
):
    """Print the contents of a remote file to standard out."""

    print_file(path)

@app.command('down', help='An alias for [bold cyan]download[/].', rich_help_panel='Remote Transfer')
@app.command(short_help='Download a file from remote to local.', rich_help_panel='Remote Transfer')
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
@app.command(short_help='Upload a file from local to remote.', rich_help_panel='Remote Transfer')
def upload(
    local_path: Annotated[Path, Argument(help='Path of local file.')],
    remote_path: Annotated[Path | None, Argument(help='Path of remote directory or file.')] = None,
):
    """
    Upload a file from local to remote.
    By default, it uploads the file to the configured SSH project path.
    """

    upload_file(local_path, remote_path)

@app.command(short_help='Mount the current challenge locally.', rich_help_panel='Remote Editing')
def mount(
    mount_point: Annotated[Path | None, Option('-p', '--point', help='Path of the mount point.')] = None,
):
    """
    Mount the configured remote project path locally onto the specified mount point.
    If no mount point is specified, it defaults to the configured mount point.
    """

    mount_remote(mount_point)

@app.command(short_help='Mount the current challenge locally and open it in the specified editor.', rich_help_panel='Remote Editing')
def edit(
    editor: Annotated[str | None, Option('-e', '--editor', help='Name of the editor to use.')] = None,
    mount_point: Annotated[Path | None, Option('-p', '--point', help='Path of the mount point.')] = None,
):
    """
    Mount the configured remote project path locally onto the specified mount point, and open it in the specified editor.

    If no editor is specified, it uses Visual Studio Code, unless otherwise configured.
    Supported editors include:
        'Cursor'
        'Emacs'
        'Google Antigravity'
        'Helix'
        'Nano'
        'Neovim'
        'Sublime Text'
        'Vim'
        'Visual Studio Code'
        'Zed'
    If no mount point is specified, it defaults to the configured mount point.
    """

    init_editor(editor, mount_point)

@app.command('agy', rich_help_panel='Remote Editing')
def antigravity():
    """Mount the current challenge locally and open it in Google Antigravity."""

    init_editor('Google Antigravity')

@app.command('code', rich_help_panel='Remote Editing')
def vscode():
    """Mount the current challenge locally and open it in Visual Studio Code."""

    init_editor('Visual Studio Code')

@app.command(rich_help_panel='Remote Editing')
def cursor():
    """Mount the current challenge locally and open it in Cursor."""

    init_editor('Cursor')

@app.command(rich_help_panel='Remote Editing')
def emacs():
    """Mount the current challenge locally and open it in Emacs."""

    init_editor('Emacs')

@app.command('hx', rich_help_panel='Remote Editing')
def helix():
    """Mount the current challenge locally and open it in Helix."""

    init_editor('Helix')

@app.command(rich_help_panel='Remote Editing')
def nano():
    """Mount the current challenge locally and open it in Nano."""

    init_editor('Nano')

@app.command('nvim', rich_help_panel='Remote Editing')
def neovim():
    """Mount the current challenge locally and open it in Neovim."""

    init_editor('Neovim')

@app.command('subl', rich_help_panel='Remote Editing')
def sublime():
    """Mount the current challenge locally and open it in Sublime Text."""

    init_editor('Sublime Text')

@app.command('vi', help='An alias for [bold cyan]vim[/].', rich_help_panel='Remote Editing')
@app.command('vim', rich_help_panel='Remote Editing')
def vim():
    """Mount the current challenge locally and open it in Vim."""

    init_editor('Vim')

@app.command(rich_help_panel='Remote Editing')
def zed(
    install: Annotated[bool, Option('-i', '--install', help='Install Zed or upgrade Zed to the latest version.')] = False,
    use_lang_servers: Annotated[bool, Option('-l', '--lang-server', help='Use ruff (linter) and ty (type checker).')] = False,
    use_mount: Annotated[bool, Option('-m', '--mount', help='Mount the remote directory locally.')] = False
):
    """Open Zed, a minimal code editor written in Rust, and connect remotely to the current challenge."""

    init_zed(install, use_lang_servers, use_mount)

@app.command(rich_help_panel='Challenge Help')
def discord():
    """Show the link to the pwn.college Discord server."""

    info(f'Click {apply_style('https://discord.gg/pwncollege')} to go to the Discord server or copy the link and paste it into your browser.')

@app.command(short_help="Show a hint for a challenge's flag.", rich_help_panel='Challenge Help')
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

@app.command(rich_help_panel='Challenge Help')
def sensai():
    """Communicate with the pwn.college SensAI assistant."""

    init_sensai()

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

@app.command(rich_help_panel='CLI Configuration')
def config(
    show_default: Annotated[bool, Option('-d', '--default', help='Show the default configuration instead.')] = False
):
    """Show the current configuration settings."""

    show_config(show_default)

@app.command(rich_help_panel='CLI Help')
def help():
    """Start a TUI to explore command documentation for the CLI. Press [bold cyan]^q[/] to quit."""

    init_tui(app)
