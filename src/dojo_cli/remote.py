"""Handles remote SSH connections."""

import os
import select
import shlex
import signal
import subprocess
import sys
import termios
import tty
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from time import monotonic

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from .client import get_remote_client
from .config import load_user_config
from .constants import XDG_BIN_HOME
from .http import authentication_available, request
from .install import (
    configured_package_manager,
    package_manager_install,
    require_executable,
)
from .log import error, info, success, warn
from .terminal import apply_style

BUFFER_SIZE = 1024
DEFAULT_PTY_SIZE = (80, 24)
DEFAULT_TERM = 'xterm-256color'
PROMPT_TIMEOUT = 10.0


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes = b''
    stderr: bytes = b''


def append_output(output: bytes, chunk: bytes, limit: int | None) -> bytes:
    """Append command output without retaining more than the requested limit."""
    if limit is None:
        return output + chunk
    return output + chunk[: max(0, limit - len(output))]


def install_openssh():
    """Install OpenSSH using the configured package manager."""
    package_manager_install(formulae=['openssh'], packages=['openssh'])


def ssh_keygen():
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')

    user_config = load_user_config()
    ssh_config = user_config['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()
    ssh_public_identity_file = ssh_identity_file.parent.joinpath(
        f'{ssh_identity_file.name}.pub'
    )

    ssh_identity_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    ssh_identity_file.parent.chmod(0o700)
    ssh_config_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    ssh_config_file.parent.chmod(0o700)

    if ssh_identity_file.is_file():
        warn(f'Identity file already exists at {ssh_identity_file}, override?')
        if input('(y/N) > ').strip()[:1].lower() != 'y':
            warn('Aborting SSH key generation!')
            return

    private_key = Ed25519PrivateKey.generate()
    ssh_identity_file.write_bytes(
        private_key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
    )
    ssh_identity_file.chmod(0o600)
    success(f'Saved SSH private key to {apply_style(ssh_identity_file)}.')

    public_key = (
        private_key.public_key()
        .public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
        .decode()
    )
    ssh_public_identity_file.write_text(public_key)
    ssh_public_identity_file.chmod(0o644)
    success(f'Saved SSH public key to {apply_style(ssh_public_identity_file)}.')

    ssh_config_file.touch()
    ssh_config_file.chmod(0o600)
    ssh_config_data = ssh_config_file.read_text()
    if f'Host {ssh_config["Host"]}' not in ssh_config_data:
        if ssh_config_data:
            ssh_config_data += '\n'
        ssh_config_data += f'Host {ssh_config["Host"]}\n'
        ssh_config_data += f'  HostName {ssh_config["HostName"]}\n'
        ssh_config_data += f'  Port {ssh_config["Port"]}\n'
        ssh_config_data += f'  User {ssh_config["User"]}\n'
        ssh_config_data += f'  IdentityFile {ssh_identity_file}\n'
        ssh_config_data += (
            f'  ServerAliveCountMax {ssh_config["ServerAliveCountMax"]}\n'
        )
        ssh_config_data += (
            f'  ServerAliveInterval {ssh_config["ServerAliveInterval"]}\n'
        )
        ssh_config_file.write_text(ssh_config_data)
        info(f'Updated SSH configuration at {apply_style(ssh_config_file)}.')

    if Path(user_config['cookie_path']).expanduser().resolve().is_file():
        response = request('/ssh_key', json={'ssh_key': public_key}).json()
        if response['success']:
            success('Successfully added public key to user settings.')
            success(
                'You can now connect to the remote server after starting a challenge.'
            )
        else:
            error(f'Something went wrong: {response["error"]}')
    else:
        ssh_key_url = f'{user_config["base_url"]}/settings#ssh-key'
        info(f'Public key: [b cyan]{public_key}[/]')
        info(
            'Not logged in, could not automatically add the public key to '
            'your user settings.'
        )
        info(
            f'Use a browser to log into '
            f'{apply_style(user_config["base_url"])} and navigate to '
            f'{apply_style(ssh_key_url)}.'
        )
        info(
            'Enter the above key into the [b cyan]Add New SSH Key[/] field, '
            'and then click [b cyan]Add[/].'
        )


def bat_file(path: Path):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        if path.is_dir():
            error(f'{apply_style(path)} is a directory.')
        elif not path.is_file():
            error(f'{apply_style(path)} is not an existing file.')
        elif not os.access(path, os.R_OK):
            error(f'Permission to read {apply_style(path)} denied.')

        completed = subprocess.run(
            [which('bat') or '/run/dojo/bin/bat', str(path)], check=False
        )
        if completed.returncode:
            raise SystemExit(completed.returncode)

    else:
        if not request('/docker').json().get('success'):
            error('No active challenge session; start a challenge!')

        client = get_remote_client()
        if client.is_dir(str(path)):
            error(f'{apply_style(path)} is a directory.')
        elif not client.is_file(str(path)):
            error(f'{apply_style(path)} is not an existing file.')

        run_cmd(shlex.join(['bat', str(path)]))


def print_file(path: Path):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        if path.is_dir():
            error(f'{apply_style(path)} is a directory.')
        elif not path.is_file():
            error(f'{apply_style(path)} is not an existing file.')
        elif not os.access(path, os.R_OK):
            error(f'Permission to read {apply_style(path)} denied.')

        sys.stdout.buffer.write(path.read_bytes())
        sys.stdout.buffer.flush()

    else:
        if not request('/docker').json().get('success'):
            error('No active challenge session; start a challenge!')

        client = get_remote_client()
        if client.is_dir(str(path)):
            error(f'{apply_style(path)} is a directory.')
        elif not client.is_file(str(path)):
            error(f'{apply_style(path)} is not an existing file.')

        try:
            sys.stdout.buffer.write(client.read_bytes(str(path)))
            sys.stdout.buffer.flush()
        except PermissionError:
            error(f'Permission to read {apply_style(path)} denied.')


def edit_path(editor: str, path: Path | None = None):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        if not path:
            if editor not in ['nano']:
                path = Path.cwd()
        elif editor in ['nano'] and path.is_dir():
            error(f'{editor} does not support opening directories.')

        completed = subprocess.run(
            [editor, str(path)] if path else [editor], check=False
        )
        if completed.returncode:
            raise SystemExit(completed.returncode)

    else:
        if not request('/docker').json().get('success'):
            error('No active challenge session; start a challenge!')
        if not path and editor not in ['nano']:
            path = Path(load_user_config()['ssh']['project_path'])
        elif editor in ['nano'] and get_remote_client().is_dir(str(path)):
            error(f'{editor} does not support opening directories.')

        run_cmd(shlex.join([editor, str(path)]) if path else editor)


def run_openssh(
    command: str | None = None,
    capture_output: bool = False,
    payload: bytes | None = None,
    pty: bool = True,
    max_output_bytes: int | None = None,
) -> CommandResult:
    ssh = require_executable(
        'ssh',
        [XDG_BIN_HOME / 'ssh', '/usr/local/bin/ssh', '/usr/bin/ssh'],
        display_name='OpenSSH',
        installer=install_openssh,
        method=configured_package_manager(),
    )

    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()
    pty_option = '-t' if pty else '-T'

    if (
        ssh_config_file.is_file()
        and f'Host {ssh_config["Host"]}' in ssh_config_file.read_text()
    ):
        ssh_args = [
            str(ssh),
            pty_option,
            '-F',
            str(ssh_config_file),
            ssh_config['Host'],
        ]
    elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith(
        '-----BEGIN OPENSSH PRIVATE KEY-----'
    ):
        ssh_args = [
            str(ssh),
            pty_option,
            '-p',
            str(ssh_config['Port']),
            '-i',
            str(ssh_identity_file),
            '-o',
            f'ServerAliveCountMax={ssh_config["ServerAliveCountMax"]}',
            '-o',
            f'ServerAliveInterval={ssh_config["ServerAliveInterval"]}',
            f'{ssh_config["User"]}@{ssh_config["HostName"]}',
        ]
    else:
        error(
            'Something went wrong with the SSH config file or the SSH key. '
            'Please make sure at least one is valid.'
        )

    if command:
        ssh_args.append(command)

    completed_process = subprocess.run(
        ssh_args, capture_output=capture_output, input=payload, check=False
    )
    stdout = completed_process.stdout or b''
    stderr = completed_process.stderr or b''
    if max_output_bytes is not None:
        stdout = stdout[:max_output_bytes]
        stderr = stderr[:max_output_bytes]
    return CommandResult(completed_process.returncode, stdout, stderr)


def run_paramiko(
    command: str | None = None,
    capture_output: bool = False,
    payload: bytes | None = None,
    pty: bool = True,
    max_output_bytes: int | None = None,
) -> CommandResult:
    with get_remote_client().get_channel() as channel:
        try:
            stdin_fd = sys.stdin.fileno()
        except AttributeError, OSError, ValueError:
            stdin_fd = None

        try:
            stdin_is_tty = stdin_fd is not None and sys.stdin.isatty()
        except OSError, ValueError:
            stdin_is_tty = False

        previous_sigwinch = None
        if pty and stdin_is_tty:
            try:
                channel.get_pty(DEFAULT_TERM, *os.get_terminal_size())
            except OSError:
                channel.get_pty(DEFAULT_TERM, *DEFAULT_PTY_SIZE)

            def resize_pty(signum, frame):
                try:
                    channel.resize_pty(*os.get_terminal_size())
                except OSError:
                    pass

            previous_sigwinch = signal.signal(signal.SIGWINCH, resize_pty)

        output = b''
        error_output = b''
        oldtty = None
        try:
            if command:
                channel.exec_command(command)
                if payload:
                    channel.sendall(payload)
                    channel.shutdown_write()
            else:
                channel.invoke_shell()
                if payload:
                    deadline = monotonic() + PROMPT_TIMEOUT
                    while not output.endswith(b'$ '):
                        remaining = deadline - monotonic()
                        if (
                            remaining <= 0
                            or not select.select([channel], [], [], remaining)[0]
                        ):
                            error('Timed out waiting for the remote shell prompt.')
                        if channel.recv_ready():
                            output += channel.recv(BUFFER_SIZE)

                    channel.sendall(payload)
                    channel.recv(len(payload) + payload.count(b'\n'))
                    output = b''

            if not capture_output:
                success('Connected!')
            if stdin_is_tty and stdin_fd is not None:
                oldtty = termios.tcgetattr(stdin_fd)
                tty.setraw(stdin_fd)
                tty.setcbreak(stdin_fd)
            channel.settimeout(0.0)

            rlist_sources = [channel]
            if not capture_output and stdin_fd is not None:
                rlist_sources.append(sys.stdin)

            while True:
                rlist = select.select(rlist_sources, [], [])[0]
                if channel in rlist:
                    try:
                        if channel.recv_ready():
                            buffer = channel.recv(BUFFER_SIZE)
                            if capture_output:
                                output = append_output(output, buffer, max_output_bytes)
                            else:
                                sys.stdout.buffer.write(buffer)
                                sys.stdout.buffer.flush()
                        if channel.recv_stderr_ready():
                            buffer = channel.recv_stderr(BUFFER_SIZE)
                            if capture_output:
                                error_output = append_output(
                                    error_output, buffer, max_output_bytes
                                )
                            else:
                                sys.stderr.buffer.write(buffer)
                                sys.stderr.buffer.flush()
                        if (
                            channel.exit_status_ready()
                            and not channel.recv_ready()
                            and not channel.recv_stderr_ready()
                        ):
                            break
                    except TimeoutError:
                        pass
                if sys.stdin in rlist:
                    assert stdin_fd is not None
                    buffer = os.read(stdin_fd, BUFFER_SIZE)
                    if not buffer:
                        if stdin_is_tty:
                            break
                        rlist_sources.remove(sys.stdin)
                        try:
                            channel.shutdown_write()
                        except AttributeError, OSError:
                            pass
                        continue
                    channel.sendall(buffer)
        finally:
            if oldtty is not None and stdin_fd is not None:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, oldtty)
            if previous_sigwinch is not None:
                signal.signal(signal.SIGWINCH, previous_sigwinch)

        return CommandResult(channel.recv_exit_status(), output, error_output)


def run_cmd(
    command: str | None = None,
    capture_output: bool = False,
    payload: bytes | None = None,
    pty: bool = True,
    client_type: str = 'paramiko',
    max_output_bytes: int | None = None,
) -> CommandResult:
    """Run a command and return its status, standard output, and standard error."""

    if client_type == 'local' or 'DOJO_AUTH_TOKEN' in os.environ:
        completed_process = subprocess.run(
            command or 'bash',
            shell=True,
            capture_output=capture_output,
            input=payload,
            check=False,
        )
        stdout = completed_process.stdout or b''
        stderr = completed_process.stderr or b''
        if max_output_bytes is not None:
            stdout = stdout[:max_output_bytes]
            stderr = stderr[:max_output_bytes]
        return CommandResult(completed_process.returncode, stdout, stderr)
    interactive = command is None and not capture_output and pty and payload is None
    if interactive and authentication_available():
        if not request('/docker').json().get('success'):
            from .tree import init_tree

            if not init_tree(auth=True):
                return CommandResult(1)
    elif not interactive and not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    if client_type == 'openssh':
        return run_openssh(command, capture_output, payload, pty, max_output_bytes)
    elif client_type == 'paramiko':
        return run_paramiko(command, capture_output, payload, pty, max_output_bytes)
    else:
        error(f'Invalid client type: {client_type}')


def download_file(
    remote_path: Path, local_path: Path | None = None, log_success: bool = True
):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    client = get_remote_client()
    if not client.is_file(str(remote_path)):
        error('Remote path is not a file.')

    if not local_path:
        local_path = Path.cwd()

    local_path = local_path.expanduser().resolve()

    if local_path.is_dir():
        local_path /= remote_path.name

    client.get(str(remote_path), str(local_path))

    if log_success:
        success(f'Downloaded {remote_path} to {local_path}')


def upload_file(
    local_path: Path, remote_path: Path | None = None, log_success: bool = True
):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    local_path = local_path.expanduser().resolve()

    if not local_path.is_file():
        error('Provided path is not a file.')

    if not remote_path:
        remote_path = Path(load_user_config()['ssh']['project_path'])

    client = get_remote_client()
    if not client.is_file(str(remote_path)):
        if client.is_dir(str(remote_path)):
            remote_path /= local_path.name
        elif not client.is_dir(str(remote_path.parent)):
            client.makedirs(str(remote_path.parent))

    client.put(str(local_path), str(remote_path))

    if log_success:
        success(f'Uploaded {local_path} to {remote_path}')
