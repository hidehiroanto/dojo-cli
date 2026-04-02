"""This is the main command line interface file."""

# TODO: add commands for solve stats
# TODO: resolve dict.get(key) vs dict[key]
# Caveat: this CLI is designed for Linux remote challenges, might work for Mac challenges idk

from pathlib import Path
from typing import Annotated, Optional

from cyclopts import App, Group, Parameter, validators
from cyclopts.types import ResolvedDirectory, ResolvedExistingFile, ResolvedPath

from .challenge import (
    init_challenge,
    init_next,
    init_previous,
    restart_challenge,
    show_hint,
    show_list,
    show_status,
    stop_challenge,
    submit_flag
)
from .config import DEFAULT_CONFIG_PATH, show_config
from .editor import init_editor, mount_remote, unmount_remote
from .log import info
from .remote import (
    bat_file,
    download_file,
    edit_path,
    print_file,
    run_cmd,
    ssh_keygen,
    upload_file
)
from .sensai import init_sensai
from .shell import init_bash, init_fish, init_nu, init_zsh
from .terminal import apply_style
from .tree import init_tree
from .tui import init_trogon
from .user import (
    change_settings,
    do_login,
    do_logout,
    do_register,
    show_activity,
    show_belts,
    show_me,
    show_score,
    show_scoreboard
)
from .video import init_twitch, init_youtube
from .zed import init_zed

app = App(
    name='dojo',
    help=f"""
    `dojo` is a Python command line interface to interact with the website and API at [pwn.college](https://pwn.college).

    Type `--help` or `-h` after `dojo <COMMAND>` to display further documentation for one of the below commands.

    Set the `DOJO_CONFIG` environment variable to override the default configuration path at `{DEFAULT_CONFIG_PATH}`.
    """,
    default_parameter=Parameter(negative=())
)

user_login = Group.create_ordered('User Login and Settings')

@app.command(group=user_login)
def register(*,
    username: Annotated[Optional[str], Parameter(alias='-u')] = None,
    email: Annotated[Optional[str], Parameter(alias='-e')] = None,
    password: Annotated[Optional[str], Parameter(alias='-p')] = None
):
    """
    Register for a new pwn.college account and save session cookie to the cache.

    Args:
        username (Optional[str]): Username
        email (Optional[str]): Email
        password (Optional[str]): Password
    """
    do_register(username, email, password)

@app.command(group=user_login)
def login(*,
    username: Annotated[Optional[str], Parameter(alias='-u')] = None,
    password: Annotated[Optional[str], Parameter(alias='-p')] = None
):
    """
    Log into your pwn.college account and save session cookie to the cache.

    Args:
        username (Optional[str]): Username or email
        password (Optional[str]): Password
    """
    do_login(username, password)

@app.command(group=user_login)
def logout():
    """Log out of your pwn.college account by deleting session cookie from the cache."""
    do_logout()

@app.command(group=user_login)
def settings():
    """Change the settings of your pwn.college account."""
    change_settings()

@app.command(group=user_login)
def keygen():
    """Generate an SSH key for the dojo and add it to user settings."""
    ssh_keygen()

user_info = Group.create_ordered('User Info')

@app.command(alias=('me', 'profile'), group=user_info)
def whoami(*, simple: Annotated[bool, Parameter(alias='-s')] = False):
    """
    Show information about the current user (you!)

    Args:
        simple (bool): Disable images
    """
    show_me(simple)

@app.command(alias=('rank', 'score'), group=user_info)
def whois(*, username: Annotated[Optional[str], Parameter(alias='-u')] = None):
    """
    Show global ranking for another user. If no username is given, show the current user's ranking.

    Args:
        username (Optional[str]): Username to query
    """
    show_score(username)

@app.command(group=user_info)
def activity(*, user_id: Annotated[Optional[int], Parameter(name='--id', alias='-i')] = None):
    """
    Show activity for another user. If no user ID is given, show the current user's activity.

    Args:
        user_id (Optional[int]): User ID
    """
    show_activity(user_id)

@app.command(group=user_info)
def scoreboard(*,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    duration: Annotated[str, Parameter(alias='-t')] = 'all',
    page: Annotated[int, Parameter(alias='-p')] = 1,
    simple: Annotated[bool, Parameter(alias='-s')] = False
):
    """
    Show scoreboard for a dojo or module. If no dojo is given, show WeChall global scoreboard.

    Args:
        dojo_id (Optional[str]): Dojo ID
        module_id (Optional[str]): Module ID
        duration (str): Scoreboard duration (week, month, all)
        page (int): Scoreboard page number
        simple (bool): Disable images
    """
    show_scoreboard(dojo_id, module_id, duration, page, simple)

@app.command(group=user_info)
def belts(*,
    belt: Annotated[Optional[str], Parameter(name='--color', alias='-c')] = None,
    page: Annotated[Optional[int], Parameter(alias='-p')] = None,
    simple: Annotated[bool, Parameter(alias='-s')] = False
):
    """
    Show all the users who have earned belts above white belt.

    Args:
        belt (Optional[str]): Filter by belt color
        page (Optional[int]): Belt list page number
        simple (bool): Disable images
    """
    show_belts(belt, page, simple)

challenge_info = Group.create_ordered('Challenge Info')

@app.command(name='list', alias='ls', group=challenge_info)
def ls(*,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    challenge_id: Annotated[Optional[str], Parameter(name='--challenge', alias='-c')] = None,
    auth: Annotated[bool, Parameter(alias='-a')] = False,
    official: Annotated[bool, Parameter(alias='-o')] = False,
    simple: Annotated[bool, Parameter(alias='-s')] = False
):
    """
    List the members of a dojo or module. If no dojo is given, display all dojos.

    Args:
        dojo_id (Optional[str]): Dojo ID
        module_id (Optional[str]): Module ID
        challenge_id (Optional[str]): Challenge ID
        auth (bool): Authenticate to display hidden dojos
        official (bool): Filter to official dojos
        simple (bool): Disable images
    """
    show_list(dojo_id, module_id, challenge_id, auth, official, simple)

@app.command(group=challenge_info)
def tree(*,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    challenge_id: Annotated[Optional[str], Parameter(name='--challenge', alias='-c')] = None,
    auth: Annotated[bool, Parameter(alias='-a')] = False,
    official: Annotated[bool, Parameter(alias='-o')] = False
):
    """
    Display a tree of the members of a dojo or module in a TUI. If no dojo is given, display a tree of all dojos.

    Args:
        dojo_id (Optional[str]): Dojo ID
        module_id (Optional[str]): Module ID
        challenge_id (Optional[str]): Challenge ID
        auth (bool): Authenticate to display hidden dojos
        official (bool): Filter to official dojos
    """
    init_tree(dojo_id, module_id, challenge_id, auth, official)

video_playback = Group.create_ordered('Video Streaming and Playback')

@app.command(alias='ttv', group=video_playback)
def twitch():
    """Play the pwn.college live stream on Twitch."""
    init_twitch()

@app.command(alias='yt', group=video_playback)
def youtube(*,
    video_id: Annotated[Optional[str], Parameter(name='--video', alias='-v')] = None,
    playlist_id: Annotated[Optional[str], Parameter(name='--playlist', alias='-p')] = None,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    resource_id: Annotated[Optional[str], Parameter(name='--resource', alias='-r')] = None,
    page: Annotated[Optional[int], Parameter(alias='-n')] = None,
    simple: Annotated[bool, Parameter(alias='-s')] = False
):
    """
    Play a lecture on YouTube.

    Args:
        video_id (Optional[str]): YouTube video ID or URL
        playlist_id (Optional[str]): YouTube playlist ID
        dojo_id (Optional[str]): Dojo ID
        module_id (Optional[str]): Module ID
        resource_id (Optional[str]): Resource ID
        page (Optional[int]): YouTube feed page number
        simple (bool): Disable thumbnails
    """
    init_youtube(video_id, playlist_id, dojo_id, module_id, resource_id, page, simple)

challenge_launch = Group.create_ordered('Challenge Launch')
challenge_mode = Group(validator=validators.mutually_exclusive)

@app.command(group=challenge_launch)
def start(*,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    challenge_id: Annotated[Optional[str], Parameter(name='--challenge', alias='-c')] = None,
    normal: Annotated[bool, Parameter(alias='-n', group=challenge_mode)] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'), group=challenge_mode)] = False
):
    """
    Start a new challenge. The challenge ID can either be by itself or in the format `<dojo>/<module>/<challenge>`.

    If no dojo or no module is given, they are inferred from the challenge ID.
    If no challenge is given, restart the current challenge.

    `--normal` and `--privileged` are mutually exclusive.
    If neither --normal nor --privileged are given, start in the current mode if a challenge is running, otherwise start in normal mode.

    Args:
        dojo_id (Optional[str]): Dojo ID
        module_id (Optional[str]): Module ID
        challenge_id (Optional[str]): Challenge ID
        normal (bool): Start in normal mode
        privileged (bool): Start in privileged mode
    """
    init_challenge(dojo_id, module_id, challenge_id, normal, privileged)

@app.command(name='next', group=challenge_launch)
def start_next(*,
    normal: Annotated[bool, Parameter(alias='-n', group=challenge_mode)] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'), group=challenge_mode)] = False
):
    """
    Start the next challenge in the current module.

    Args:
        normal (bool): Start in normal mode.
        privileged (bool): Start in privileged mode.
    """
    init_next(normal, privileged)

@app.command(alias='prev', group=challenge_launch)
def previous(*,
    normal: Annotated[bool, Parameter(alias='-n', group=challenge_mode)] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'), group=challenge_mode)] = False
):
    """
    Start the previous challenge in the current module.

    Args:
        normal (bool): Start in normal mode.
        privileged (bool): Start in privileged mode.
    """
    init_previous(normal, privileged)

@app.command(group=challenge_launch)
def restart(*,
    normal: Annotated[bool, Parameter(alias='-n', group=challenge_mode)] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'), group=challenge_mode)] = False
):
    """
    Restart the current challenge. This will restart in the current mode by default.

    Args:
        normal (bool): Restart in normal mode.
        privileged (bool): Restart in privileged mode.
    """
    restart_challenge(normal, privileged)

@app.command(group=challenge_launch)
def stop():
    """Stop the current challenge."""
    stop_challenge()

challenge_status = Group.create_ordered('Challenge Status')

@app.command(alias='ps', group=challenge_status)
def status():
    """Show the status of the current challenge."""
    show_status()

remote_connection = Group.create_ordered('Remote Connection')

@app.command(group=remote_connection)
def connect():
    """Connect to the current challenge via an interactive remote shell (bash by default)."""
    run_cmd()

@app.command(group=remote_connection)
def bash(*, command_string: Annotated[Optional[str], Parameter(name='-c')] = None):
    """
    Connect to the current challenge via a bash login shell.

    Args:
        command_string (Optional[str]): Run the given command and then exit.
    """
    init_bash(command_string)

@app.command(group=remote_connection)
def fish(*,
    command: Annotated[Optional[str], Parameter(alias='-c')] = None,
    init_command: Annotated[Optional[str], Parameter(alias='-C')] = None
):
    """
    Connect to the current challenge via a fish login shell.

    Args:
        command (Optional[str]): Run the given command and then exit.
        init_command (Optional[str]): Run the given command and then enter an interactive shell.
    """
    init_fish(command, init_command)

@app.command(group=remote_connection)
def nu(*,
    commands: Annotated[Optional[str], Parameter(alias='-c')] = None,
    exec_commands: Annotated[Optional[str], Parameter(name='--execute', alias='-e')] = None
):
    """
    Connect to the current challenge via a nushell login shell.

    Args:
        commands (Optional[str]): Run the given commands and then exit.
        exec_commands (Optional[str]): Run the given commands and then enter an interactive shell.
    """
    init_nu(commands, exec_commands)

@app.command(group=remote_connection)
def tmux():
    """Connect to the current challenge via a tmux login shell."""
    run_cmd('tmux -l')

@app.command(group=remote_connection)
def zellij():
    """Connect to the current challenge via zellij."""
    run_cmd('zellij')

@app.command(group=remote_connection)
def zsh(*, command: Annotated[Optional[str], Parameter(name='-c')] = None):
    """
    Connect to the current challenge via a zsh login shell.

    Args:
        command (Optional[str]): Run the given command and then exit.
    """
    init_zsh(command)

remote_execution = Group.create_ordered('Remote Execution')

@app.command(alias=('ssh', 'exec'), group=remote_execution)
def run(command: Optional[str] = None, /):
    """
    Execute a remote command. If no command is given, start a shell like `connect`.

    Args:
        command (Optional[str]): The command to run
    """
    run_cmd(command)

@app.command(group=remote_execution)
def du(*,
    path: Annotated[Optional[Path], Parameter(alias='-p')] = None,
    count: Annotated[int, Parameter(name='--lines', alias='-n')] = 20
):
    """
    List the largest files in a directory, using `du`. Helpful when clearing up space.

    Args:
        path (Optional[Path]): Path to list files from.
        count (int): Number of files to display.
    """
    run_cmd(f'find {path or '~'} -type f -exec du -hs {{}} + 2>/dev/null | sort -hr | head -n {count}')

@app.command(group=remote_execution)
def dust(*,
    path: Annotated[Optional[Path], Parameter(alias='-p')] = None,
    count: Annotated[int, Parameter(name='--lines', alias='-n')] = 20
):
    """
    List the largest files in a directory, using `dust`. Helpful when clearing up space.

    Args:
        path (Optional[Path]): Path to list files from.
        count (int): Number of files to display.
    """
    run_cmd(f'dust -CFprsx -n {count} {path or '~'} 2>/dev/null')

remote_transfer = Group.create_ordered('Remote Transfer')

@app.command(group=remote_transfer)
def bat(path: Path, /):
    """
    Print the contents of a remote file to standard out using `bat`.

    Args:
        path (Path): The file to print.
    """
    bat_file(path)

@app.command(group=remote_transfer)
def cat(path: Path, /):
    """
    Print the contents of a remote file to standard out.

    Args:
        path (Path): The file to print.
    """
    print_file(path)

@app.command(alias='down', group=remote_transfer)
def download(remote_path: Path, local_path: Optional[ResolvedPath] = None, /):
    """
    Download a file from remote to local.
    By default, it downloads the file to the current working directory.

    Args:
        remote_path (Path): Path of remote file.
        local_path (Optional[ResolvedPath]): Path of local directory or file.
    """
    download_file(remote_path, local_path)

@app.command(alias='up', group=remote_transfer)
def upload(local_path: ResolvedExistingFile, remote_path: Optional[Path] = None, /):
    """
    Upload a file from local to remote.
    By default, it uploads the file to the configured SSH project path.

    Args:
        local_path (ResolvedExistingFile): Path of local file.
        remote_path (Optional[Path]): Path of remote directory or file.
    """
    upload_file(local_path, remote_path)

remote_mount = Group.create_ordered('Remote Mounting')

@app.command(group=remote_mount)
def mount(*, mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None):
    """
    Mount the configured remote project path locally onto the specified mount point.

    If no mount point is specified, it defaults to the configured mount point.

    Args:
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    mount_remote(mount_point)

@app.command(alias='umount', group=remote_mount)
def unmount(*, mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None):
    """
    Unmount the filesystem at the specified mount point.

    If no mount point is specified, it defaults to the configured mount point.

    Args:
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    unmount_remote(mount_point)

remote_edit = Group.create_ordered('Remote Editing')

@app.command(group=remote_edit)
def edit(
    path: Optional[Path] = None, /, *,
    editor: Annotated[Optional[str], Parameter(alias='-e')] = None,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally onto the given mount point, and open the given path in the given editor.

    If no path is specified, it defaults to the mount point.
    If no editor is specified, it uses Visual Studio Code, unless otherwise configured.
    Supported editors include:
        'CodeEdit' (macOS only, very broken)
        'Cursor'
        'Eclipse Theia' (macOS only for now)
        'Emacs'
        'Google Antigravity'
        'Helix'
        'Kakoune'
        'Lapce'
        'Micro'
        'Nano'
        'Neovim'
        'PyCharm'
        'Sublime Text'
        'TextMate'
        'Vim'
        'Visual Studio Code'
        'VSCodium'
        'Windsurf'
        'Zed'
    If no mount point is specified, it defaults to the configured mount point.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        editor (Optional[str]): Name of the editor to use.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor(editor, path, mount_point)

@app.command(alias='agy', group=remote_edit)
def antigravity(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Google Antigravity.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Google Antigravity', path, mount_point)

@app.command(group=remote_edit)
def codeedit(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in CodeEdit. (macOS only, very broken)

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('CodeEdit', path, mount_point)

@app.command(group=remote_edit)
def cursor(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Cursor.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Cursor', path, mount_point)

@app.command(group=remote_edit)
def emacs(path: Optional[Path] = None, /):
    """
    Open a remote directory or file in Emacs.

    Args:
        path (Optional[Path]): The path to open.
    """
    edit_path('emacs', path)

@app.command(alias='hx', group=remote_edit)
def helix(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Helix.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Helix', path, mount_point)

@app.command(alias='kak', group=remote_edit)
def kakoune(path: Path, /, *, mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None):
    """
    Mount the current challenge locally and open a mounted file in Kakoune.

    Args:
        path (Path): The file path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Kakoune', path, mount_point)

@app.command(group=remote_edit)
def lapce(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Lapce.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Lapce', path, mount_point)

@app.command(group=remote_edit)
def micro(path: Path, /, *, mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None):
    """
    Mount the current challenge locally and open a mounted file in Micro.

    Args:
        path (Path): The file path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Micro', path, mount_point)

@app.command(group=remote_edit)
def nano(path: Path, /):
    """
    Open a remote file in Nano.

    Args:
        path (Path): The file path to open.
    """
    edit_path('nano', path)

@app.command(alias='nvim', group=remote_edit)
def neovim(path: Optional[Path] = None, /):
    """
    Open a remote directory or file in Neovim.

    Args:
        path (Optional[Path]): The path to open.
    """
    edit_path('nvim', path)

@app.command(group=remote_edit)
def pycharm(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in PyCharm.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('PyCharm', path, mount_point)

@app.command(alias='subl', group=remote_edit)
def sublime(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Sublime Text.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Sublime Text', path, mount_point)

@app.command(alias='mate', group=remote_edit)
def textmate(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in TextMate.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('TextMate', path, mount_point)

@app.command(group=remote_edit)
def theia(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Eclipse Theia. (macOS only for now)

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Eclipse Theia', path, mount_point)

@app.command(alias='vi', group=remote_edit)
def vim(path: Optional[Path] = None, /):
    """
    Open a remote directory or file in Vim.

    Args:
        path (Optional[Path]): The path to open.
    """
    edit_path('vim', path)

@app.command(alias='code', group=remote_edit)
def vscode(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Visual Studio Code.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Visual Studio Code', path, mount_point)

@app.command(alias='codium', group=remote_edit)
def vscodium(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in VSCodium.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('VSCodium', path, mount_point)

@app.command(alias='surf', group=remote_edit)
def windsurf(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[ResolvedDirectory], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Windsurf.

    Args:
        path (Optional[Path]): The path to open, relative to the mount point.
        mount_point (Optional[ResolvedDirectory]): Path of the mount point.
    """
    init_editor('Windsurf', path, mount_point)

@app.command(group=remote_edit)
def zed(*,
    install: Annotated[bool, Parameter(alias='-i')] = False,
    use_lang_servers: Annotated[bool, Parameter(name='--lang-server', alias='-l')] = False,
    use_mount: Annotated[bool, Parameter(name='--mount', alias='-m')] = False
):
    """
    Open Zed, a minimal code editor written in Rust, and connect remotely to the current challenge.

    Args:
        install (bool): Install Zed or upgrade Zed to the latest version.
        use_lang_servers (bool): Use ruff (linter) and ty (type checker).
        use_mount (bool): Mount the remote directory locally.
    """
    init_editor('Zed') if use_mount else init_zed(install, use_lang_servers)

challenge_help = Group.create_ordered('Challenge Help')

@app.command(group=challenge_help)
def discord():
    """Show the link to the pwn.college Discord server."""
    info(f'Click {apply_style('https://discord.gg/pwncollege')} to go to the Discord server or copy the link and paste it into your browser.')

@app.command(group=challenge_help)
def hint(*,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    challenge_id: Annotated[Optional[str], Parameter(name='--challenge', alias='-c')] = None
):
    """
    Show a hint for a challenge's flag.
    If no dojo or no module is given, they are inferred from the challenge ID.

    If no challenge is given, the hint will be provided for the current challenge's flag.

    Args:
        dojo_id (Optional[str]): Dojo ID
        module_id (Optional[str]): Module ID
        challenge_id (Optional[str]): Challenge ID
    """
    show_hint(dojo_id, module_id, challenge_id)

@app.command(group=challenge_help)
def sensai(*, simple: Annotated[bool, Parameter(alias='-s')] = False):
    """
    Communicate with the pwn.college SensAI assistant.

    Args:
        simple (bool): Disable TUI
    """
    init_sensai(simple)

flag_submit = Group.create_ordered('Flag Submission')

@app.command(alias='submit', group=flag_submit)
def solve(*,
    flag: Annotated[Optional[str], Parameter(alias='-f')] = None,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    challenge_id: Annotated[Optional[str], Parameter(name='--challenge', alias='-c')] = None
):
    """
    Submit a flag for a challenge. Warns if flag is for wrong user or challenge.

    If no dojo or no module is given, they are inferred from the challenge ID.
    If no challenge is given, the flag will be submitted for the current challenge.

    Args:
        flag (Optional[str]): Flag to submit.
        dojo_id (Optional[str]): Dojo ID
        module_id (Optional[str]): Module ID
        challenge_id (Optional[str]): Challenge ID
    """
    submit_flag(flag, dojo_id, module_id, challenge_id)

cli_config = Group.create_ordered('CLI Configuration')

@app.command(group=cli_config)
def config(*, show_default: Annotated[bool, Parameter(name='--default', alias='-d')] = False):
    """
    Show the current configuration settings.

    Args:
        show_default (bool): Show the default configuration instead.
    """
    show_config(show_default)

cli_help = Group.create_ordered('CLI Help')

@app.command(alias='trogon', group=cli_help)
def help():
    """Start a TUI to explore command documentation for the CLI. Press `^q` to quit."""
    init_trogon(app)
