"""This is the main command line interface file."""

# TODO: add commands for solve stats
# TODO: resolve dict.get(key) vs dict[key]
# Caveat: this CLI is designed for Linux remote challenges, might work for Mac challenges idk

from cyclopts import App, Group, Parameter
from pathlib import Path
from typing import Annotated, Optional

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

GROUPS = {name: Group.create_ordered(name) for name in (
    'User Login and Settings',
    'User Info',
    'Challenge Info',
    'Video Streaming and Playback',
    'Challenge Launch',
    'Challenge Status',
    'Remote Connection',
    'Remote Execution',
    'Remote Transfer',
    'Remote Mounting',
    'Remote Editing',
    'Challenge Help',
    'Flag Submission',
    'CLI Configuration',
    'CLI Help'
)}

@app.command(group=GROUPS['User Login and Settings'])
def register(*,
    username: Annotated[Optional[str], Parameter(alias='-u')] = None,
    email: Annotated[Optional[str], Parameter(alias='-e')] = None,
    password: Annotated[Optional[str], Parameter(alias='-p')] = None
):
    """
    Register for a new pwn.college account and save session cookie to the cache.

    Args:
        username: Username
        email: Email
        password: Password
    """
    do_register(username, email, password)

@app.command(group=GROUPS['User Login and Settings'])
def login(*,
    username: Annotated[Optional[str], Parameter(alias='-u')] = None,
    password: Annotated[Optional[str], Parameter(alias='-p')] = None
):
    """
    Log into your pwn.college account and save session cookie to the cache.

    Args:
        username: Username or email
        password: Password
    """
    do_login(username, password)

@app.command(group=GROUPS['User Login and Settings'])
def logout():
    """Log out of your pwn.college account by deleting session cookie from the cache."""
    do_logout()

@app.command(group=GROUPS['User Login and Settings'])
def settings():
    """Change the settings of your pwn.college account."""
    change_settings()

@app.command(group=GROUPS['User Login and Settings'])
def keygen():
    """Generate an SSH key for the dojo and add it to user settings."""
    ssh_keygen()

@app.command(alias=('me', 'profile'), group=GROUPS['User Info'])
def whoami(*, simple: Annotated[bool, Parameter(alias='-s')] = False):
    """
    Show information about the current user (you!)

    Args:
        simple: Disable images
    """
    show_me(simple)

@app.command(alias=('rank', 'score'), group=GROUPS['User Info'])
def whois(*, username: Annotated[Optional[str], Parameter(alias='-u')] = None):
    """
    Show global ranking for another user. If no username is given, show the current user's ranking.

    Args:
        username: Username to query
    """
    show_score(username)

@app.command(group=GROUPS['User Info'])
def activity(*, user_id: Annotated[Optional[int], Parameter(name='--id', alias='-i')] = None):
    """
    Show activity for another user. If no user ID is given, show the current user's activity.

    Args:
        user_id: User ID
    """
    show_activity(user_id)

@app.command(group=GROUPS['User Info'])
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
        dojo_id: Dojo ID
        module_id: Module ID
        duration: Scoreboard duration (week, month, all)
        page: Scoreboard page number
        simple: Disable images
    """
    show_scoreboard(dojo_id, module_id, duration, page, simple)

@app.command(group=GROUPS['User Info'])
def belts(*,
    belt: Annotated[Optional[str], Parameter(name='--color', alias='-c')] = None,
    page: Annotated[Optional[int], Parameter(alias='-p')] = None,
    simple: Annotated[bool, Parameter(alias='-s')] = False
):
    """
    Show all the users who have earned belts above white belt.

    Args:
        belt: Filter by belt color
        page: Belt list page number
        simple: Disable images
    """
    show_belts(belt, page, simple)

@app.command(name='list', alias='ls', group=GROUPS['Challenge Info'])
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
        dojo_id: Dojo ID
        module_id: Module ID
        challenge_id: Challenge ID
        auth: Authenticate to display hidden dojos
        official: Filter to official dojos
        simple: Disable images
    """
    show_list(dojo_id, module_id, challenge_id, auth, official, simple)

@app.command(group=GROUPS['Challenge Info'])
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
        dojo_id: Dojo ID
        module_id: Module ID
        challenge_id: Challenge ID
        auth: Authenticate to display hidden dojos
        official: Filter to official dojos
    """
    init_tree(dojo_id, module_id, challenge_id, auth, official)

@app.command(alias='ttv', group=GROUPS['Video Streaming and Playback'])
def twitch():
    """Play the pwn.college live stream on Twitch."""
    init_twitch()

@app.command(alias='yt', group=GROUPS['Video Streaming and Playback'])
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
        video_id: YouTube video ID or URL
        playlist_id: YouTube playlist ID
        dojo_id: Dojo ID
        module_id: Module ID
        resource_id: Resource ID
        page: YouTube feed page number
        simple: Disable thumbnails
    """
    init_youtube(video_id, playlist_id, dojo_id, module_id, resource_id, page, simple)

@app.command(group=GROUPS['Challenge Launch'])
def start(*,
    dojo_id: Annotated[Optional[str], Parameter(name='--dojo', alias='-d')] = None,
    module_id: Annotated[Optional[str], Parameter(name='--module', alias='-m')] = None,
    challenge_id: Annotated[Optional[str], Parameter(name='--challenge', alias='-c')] = None,
    normal: Annotated[bool, Parameter(alias='-n')] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'))] = False
):
    """
    Start a new challenge. The challenge ID can either be by itself or in the format `<dojo>/<module>/<challenge>`.

    If no dojo or no module is given, they are inferred from the challenge ID.
    If no challenge is given, restart the current challenge.

    If both --normal and --privileged are given, --privileged takes precedence.
    If neither --normal nor --privileged are given, start in the current mode if a challenge is running, otherwise start in normal mode.

    Args:
        dojo_id: Dojo ID
        module_id: Module ID
        challenge_id: Challenge ID
        normal: Start in normal mode
        privileged: Start in privileged mode
    """
    init_challenge(dojo_id, module_id, challenge_id, normal, privileged)

@app.command(name='next', group=GROUPS['Challenge Launch'])
def start_next(*,
    normal: Annotated[bool, Parameter(alias='-n')] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'))] = False
):
    """
    Start the next challenge in the current module.

    Args:
        normal: Start in normal mode.
        privileged: Start in privileged mode.
    """
    init_next(normal, privileged)

@app.command(alias='prev', group=GROUPS['Challenge Launch'])
def previous(*,
    normal: Annotated[bool, Parameter(alias='-n')] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'))] = False
):
    """
    Start the previous challenge in the current module.

    Args:
        normal: Start in normal mode.
        privileged: Start in privileged mode.
    """
    init_previous(normal, privileged)

@app.command(group=GROUPS['Challenge Launch'])
def restart(*,
    normal: Annotated[bool, Parameter(alias='-n')] = False,
    privileged: Annotated[bool, Parameter(alias=('--practice', '-p'))] = False
):
    """
    Restart the current challenge. This will restart in the current mode by default.

    Args:
        normal: Restart in normal mode.
        privileged: Restart in privileged mode.
    """
    restart_challenge(normal, privileged)

@app.command(group=GROUPS['Challenge Launch'])
def stop():
    """Stop the current challenge."""
    stop_challenge()

@app.command(alias='ps', group=GROUPS['Challenge Status'])
def status():
    """Show the status of the current challenge."""
    show_status()

@app.command(group=GROUPS['Remote Connection'])
def connect():
    """Connect to the current challenge via an interactive remote shell (bash by default)."""
    run_cmd()

@app.command(group=GROUPS['Remote Connection'])
def bash(*, command_string: Annotated[Optional[str], Parameter(name='-c')] = None):
    """
    Connect to the current challenge via a bash login shell.

    Args:
        command_string: Run the given command and then exit.
    """
    init_bash(command_string)

@app.command(group=GROUPS['Remote Connection'])
def fish(*,
    command: Annotated[Optional[str], Parameter(alias='-c')] = None,
    init_command: Annotated[Optional[str], Parameter(alias='-C')] = None
):
    """
    Connect to the current challenge via a fish login shell.

    Args:
        command: Run the given command and then exit.
        init_command: Run the given command and then enter an interactive shell.
    """
    init_fish(command, init_command)

@app.command(group=GROUPS['Remote Connection'])
def nu(*,
    commands: Annotated[Optional[str], Parameter(alias='-c')] = None,
    exec_commands: Annotated[Optional[str], Parameter(name='--execute', alias='-e')] = None
):
    """
    Connect to the current challenge via a nushell login shell.

    Args:
        commands: Run the given commands and then exit.
        exec_commands: Run the given commands and then enter an interactive shell.
    """
    init_nu(commands, exec_commands)

@app.command(group=GROUPS['Remote Connection'])
def tmux():
    """Connect to the current challenge via a tmux login shell."""
    run_cmd('tmux -l')

@app.command(group=GROUPS['Remote Connection'])
def zellij():
    """Connect to the current challenge via zellij."""
    run_cmd('zellij')

@app.command(group=GROUPS['Remote Connection'])
def zsh(*, command: Annotated[Optional[str], Parameter(name='-c')] = None):
    """
    Connect to the current challenge via a zsh login shell.

    Args:
        command: Run the given command and then exit.
    """
    init_zsh(command)

@app.command(alias=('ssh', 'exec'), group=GROUPS['Remote Execution'])
def run(command: Optional[str] = None, /):
    """
    Execute a remote command. If no command is given, start a shell like `connect`.

    Args:
        command: The command to run
    """
    run_cmd(command)

@app.command(group=GROUPS['Remote Execution'])
def du(*,
    path: Annotated[Optional[Path], Parameter(alias='-p')] = None,
    count: Annotated[int, Parameter(name='--lines', alias='-n')] = 20
):
    """
    List the largest files in a directory, using `du`. Helpful when clearing up space.

    Args:
        path: Path to list files from.
        count: Number of files to display.
    """
    run_cmd(f'find {path or '~'} -type f -exec du -hs {{}} + 2>/dev/null | sort -hr | head -n {count}')

@app.command(group=GROUPS['Remote Execution'])
def dust(*,
    path: Annotated[Optional[Path], Parameter(alias='-p')] = None,
    count: Annotated[int, Parameter(name='--lines', alias='-n')] = 20
):
    """
    List the largest files in a directory, using `dust`. Helpful when clearing up space.

    Args:
        path: Path to list files from.
        count: Number of files to display.
    """
    run_cmd(f'dust -CFprsx -n {count} {path or '~'} 2>/dev/null')

@app.command(group=GROUPS['Remote Transfer'])
def bat(path: Path, /):
    """
    Print the contents of a remote file to standard out using `bat`.

    Args:
        path: The file to print.
    """
    bat_file(path)

@app.command(group=GROUPS['Remote Transfer'])
def cat(path: Path, /):
    """
    Print the contents of a remote file to standard out.

    Args:
        path: The file to print.
    """
    print_file(path)

@app.command(alias='down', group=GROUPS['Remote Transfer'])
def download(remote_path: Path, local_path: Optional[Path] = None, /):
    """
    Download a file from remote to local.
    By default, it downloads the file to the current working directory.

    Args:
        remote_path: Path of remote file.
        local_path: Path of local directory or file.
    """
    download_file(remote_path, local_path)

@app.command(alias='up', group=GROUPS['Remote Transfer'])
def upload(local_path: Path, remote_path: Optional[Path] = None, /):
    """
    Upload a file from local to remote.
    By default, it uploads the file to the configured SSH project path.

    Args:
        local_path: Path of local file.
        remote_path: Path of remote directory or file.
    """
    upload_file(local_path, remote_path)

@app.command(group=GROUPS['Remote Mounting'])
def mount(*, mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None):
    """
    Mount the configured remote project path locally onto the specified mount point.
    If no mount point is specified, it defaults to the configured mount point.

    Args:
        mount_point: Path of the mount point.
    """
    mount_remote(mount_point)

@app.command(alias='umount', group=GROUPS['Remote Mounting'])
def unmount(*, mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None):
    """
    Unmount the filesystem at the specified mount point.
    If no mount point is specified, it defaults to the configured mount point.

    Args:
        mount_point: Path of the mount point.
    """
    unmount_remote(mount_point)

@app.command(group=GROUPS['Remote Editing'])
def edit(
    path: Optional[Path] = None, /, *,
    editor: Annotated[Optional[str], Parameter(alias='-e')] = None,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
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
        path: The path to open, relative to the mount point.
        editor: Name of the editor to use.
        mount_point: Path of the mount point.
    """
    init_editor(editor, path, mount_point)

@app.command(alias='agy', group=GROUPS['Remote Editing'])
def antigravity(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Google Antigravity.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Google Antigravity', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def codeedit(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in CodeEdit. (macOS only, very broken)

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('CodeEdit', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def cursor(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Cursor.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Cursor', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def emacs(path: Optional[Path] = None, /):
    """
    Open a remote directory or file in Emacs.

    Args:
        path: The path to open.
    """
    edit_path('emacs', path)

@app.command(alias='hx', group=GROUPS['Remote Editing'])
def helix(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Helix.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Helix', path, mount_point)

@app.command(alias='kak', group=GROUPS['Remote Editing'])
def kakoune(path: Path, /, *, mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None):
    """
    Mount the current challenge locally and open a mounted file in Kakoune.

    Args:
        path: The file path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Kakoune', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def lapce(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Lapce.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Lapce', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def micro(path: Path, /, *, mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None):
    """
    Mount the current challenge locally and open a mounted file in Micro.

    Args:
        path: The file path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Micro', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def nano(path: Path, /):
    """
    Open a remote file in Nano.

    Args:
        path: The file path to open.
    """
    edit_path('nano', path)

@app.command(alias='nvim', group=GROUPS['Remote Editing'])
def neovim(path: Optional[Path] = None, /):
    """
    Open a remote directory or file in Neovim.

    Args:
        path: The path to open.
    """
    edit_path('nvim', path)

@app.command(group=GROUPS['Remote Editing'])
def pycharm(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in PyCharm.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('PyCharm', path, mount_point)

@app.command(alias='subl', group=GROUPS['Remote Editing'])
def sublime(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Sublime Text.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Sublime Text', path, mount_point)

@app.command(alias='mate', group=GROUPS['Remote Editing'])
def textmate(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in TextMate.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('TextMate', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def theia(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Eclipse Theia. (macOS only for now)

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Eclipse Theia', path, mount_point)

@app.command(alias='vi', group=GROUPS['Remote Editing'])
def vim(path: Optional[Path] = None, /):
    """
    Open a remote directory or file in Vim.

    Args:
        path: The path to open.
    """
    edit_path('vim', path)

@app.command(alias='code', group=GROUPS['Remote Editing'])
def vscode(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Visual Studio Code.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Visual Studio Code', path, mount_point)

@app.command(alias='codium', group=GROUPS['Remote Editing'])
def vscodium(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in VSCodium.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('VSCodium', path, mount_point)

@app.command(alias='surf', group=GROUPS['Remote Editing'])
def windsurf(
    path: Optional[Path] = None, /, *,
    mount_point: Annotated[Optional[Path], Parameter(name='--point', alias='-p')] = None
):
    """
    Mount the current challenge locally and open it in Windsurf.

    Args:
        path: The path to open, relative to the mount point.
        mount_point: Path of the mount point.
    """
    init_editor('Windsurf', path, mount_point)

@app.command(group=GROUPS['Remote Editing'])
def zed(*,
    install: Annotated[bool, Parameter(alias='-i')] = False,
    use_lang_servers: Annotated[bool, Parameter(name='--lang-server', alias='-l')] = False,
    use_mount: Annotated[bool, Parameter(name='--mount', alias='-m')] = False
):
    """
    Open Zed, a minimal code editor written in Rust, and connect remotely to the current challenge.

    Args:
        install: Install Zed or upgrade Zed to the latest version.
        use_lang_servers: Use ruff (linter) and ty (type checker).
        use_mount: Mount the remote directory locally.
    """
    init_editor('Zed') if use_mount else init_zed(install, use_lang_servers)

@app.command(group=GROUPS['Challenge Help'])
def discord():
    """Show the link to the pwn.college Discord server."""
    info(f'Click {apply_style('https://discord.gg/pwncollege')} to go to the Discord server or copy the link and paste it into your browser.')

@app.command(group=GROUPS['Challenge Help'])
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
        dojo_id: Dojo ID
        module_id: Module ID
        challenge_id: Challenge ID
    """
    show_hint(dojo_id, module_id, challenge_id)

@app.command(group=GROUPS['Challenge Help'])
def sensai(*, simple: Annotated[bool, Parameter(alias='-s')] = False):
    """
    Communicate with the pwn.college SensAI assistant.

    Args:
        simple: Disable TUI
    """
    init_sensai(simple)

@app.command(alias='submit', group=GROUPS['Flag Submission'])
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
        flag: Flag to submit.
        dojo_id: Dojo ID
        module_id: Module ID
        challenge_id: Challenge ID
    """
    submit_flag(flag, dojo_id, module_id, challenge_id)

@app.command(group=GROUPS['CLI Configuration'])
def config(*, show_default: Annotated[bool, Parameter(name='--default', alias='-d')] = False):
    """
    Show the current configuration settings.

    Args:
        show_default: Show the default configuration instead.
    """
    show_config(show_default)

@app.command(group=GROUPS['CLI Help'])
def help():
    """Start a TUI to explore command documentation for the CLI. Press `^q` to quit."""
    init_trogon(app)
