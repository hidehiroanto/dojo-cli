"""
Handles remote SSH connections.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
import os
from pathlib import Path
import select
from shutil import which
import signal
import stat
import subprocess
import sys
import termios
import tty

from .client import RemoteClient
from .config import load_user_config
from .http import request
from .log import error, info, success, warn
from .terminal import apply_style

BUFFER_SIZE = 1024
DEFAULT_PTY_SIZE = (80, 24)
DEFAULT_TERM = 'xterm-256color'

#TODO: move all of this into the RemoteClient class from client.py and use that instead
remote_client = None

def get_remote_client() -> RemoteClient:
    global remote_client
    if not remote_client:
        remote_client = RemoteClient()
    return remote_client

def ssh_chmod(path: Path | str, mode: int):
    get_remote_client().chmod(str(path), mode)

def ssh_getsize(path: Path | str) -> int:
    try:
        sftp_client = get_remote_client().sftp
        stat_result = sftp_client.stat(str(path))
        if stat.S_ISDIR(stat_result.st_mode):
            return sum(ssh_getsize(Path(path) / child) for child in sftp_client.listdir(str(path)))
        elif stat.S_ISREG(stat_result.st_mode):
            return stat_result.st_size
        else:
            return -1
    except FileNotFoundError:
        return -1

def ssh_is_dir(path: Path | str) -> bool:
    try:
        return stat.S_ISDIR(get_remote_client().sftp.stat(str(path)).st_mode)
    except FileNotFoundError:
        return False

def ssh_is_file(path: Path | str) -> bool:
    try:
        return stat.S_ISREG(get_remote_client().sftp.stat(str(path)).st_mode)
    except FileNotFoundError:
        return False

def ssh_listdir(path: Path | str) -> list[str]:
    return get_remote_client().sftp.listdir(str(path))

def ssh_mkdir(path: Path | str):
    """This is identical to running f'mkdir -p {path}' remotely."""

    client = get_remote_client()
    for parent in Path(path).parents[::-1]:
        if not ssh_is_dir(parent):
            client.mkdir(str(parent), 0o755)
    if not ssh_is_dir(path):
        client.mkdir(str(path), 0o755)

def ssh_read(path: Path | str) -> bytes:
    with get_remote_client().sftp.open(str(path)) as file:
        return file.read()

def ssh_remove(path: Path | str):
    get_remote_client().unlink(str(path))

def ssh_rmdir(path: Path | str):
    """This is identical to running f'rm -r {path}' remotely."""

    client = get_remote_client()
    sftp_client = client.sftp
    for child in sftp_client.listdir(str(path)):
        child_path = Path(path) / child
        if ssh_is_dir(child_path):
            ssh_rmdir(child_path)
        else:
            client.unlink(str(child_path))
    client.rmdir(str(path))

def ssh_write(path: Path | str, data: bytes) -> int:
    with get_remote_client().sftp.open(str(path), 'r+') as file:
        file.write(data)
        return len(data)

def ssh_keygen():
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')

    user_config = load_user_config()
    ssh_config = user_config['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()
    ssh_public_identity_file = ssh_identity_file.parent.joinpath(f'{ssh_identity_file.name}.pub')

    if ssh_identity_file.is_file():
        warn(f'Identity file already exists at {ssh_identity_file}, override?')
        if input('(y/N) > ').strip()[:1].lower() != 'y':
            warn('Aborting SSH key generation!')
            return

    private_key = Ed25519PrivateKey.generate()
    ssh_identity_file.touch(0o600)
    ssh_identity_file.write_bytes(private_key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()))
    success(f'Saved SSH private key to {apply_style(ssh_identity_file)}.')

    public_key = private_key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    ssh_public_identity_file.touch(0o644)
    ssh_public_identity_file.write_text(public_key)
    success(f'Saved SSH public key to {apply_style(ssh_public_identity_file)}.')

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
        info(f'Updated SSH configuration at {apply_style(ssh_config_file)}.')

    if Path(user_config['cookie_path']).expanduser().resolve().is_file():
        response = request('/ssh_key', json={'ssh_key': public_key}).json()
        if response['success']:
            success('Successfully added public key to user settings.')
            success('You can now connect to the remote server after starting a challenge.')
        else:
            error(f'Something went wrong: {response['error']}')
    else:
        ssh_key_url = f'{user_config['base_url']}/settings#ssh-key'
        info(f'Public key: [bold cyan]{public_key}[/]')
        info('Not logged in, could not automatically add the public key to your user settings.')
        info(f'Use a browser to log into {apply_style(user_config['base_url'])} and navigate to {apply_style(ssh_key_url)}.')
        info('Enter the above key into the [bold cyan]Add New SSH Key[/] field, and then click [bold cyan]Add[/].')

def bat_file(path: Path):
    if ssh_is_dir(path):
        error(f'{apply_style(path)} is a directory.')
    elif not ssh_is_file(path):
        error(f'{apply_style(path)} is not an existing file.')

    run_cmd(f'bat {path}')

def print_file(path: Path):
    if ssh_is_dir(path):
        error(f'{apply_style(path)} is a directory.')
    elif not ssh_is_file(path):
        error(f'{apply_style(path)} is not an existing file.')

    try:
        sys.stdout.buffer.write(ssh_read(path))
        sys.stdout.buffer.flush()
    except PermissionError:
        error(f'Permission to read {apply_style(path)} denied.')

def run_openssh(command: str | None = None, capture_output: bool = False, payload: bytes | None = None) -> bytes | None:
    ssh = Path(which('ssh') or '/usr/bin/ssh')
    if not ssh.is_file():
        error('Please install OpenSSH first.')

    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser().resolve()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser().resolve()

    if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
        ssh_argv = [ssh, '-F', ssh_config_file, '-t', ssh_config['Host']]
    elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
        ssh_argv = [
            ssh, '-i', ssh_identity_file, '-t',
            '-o', f'ServerAliveCountMax={ssh_config['ServerAliveCountMax']}',
            '-o', f'ServerAliveInterval={ssh_config['ServerAliveInterval']}',
            f'{ssh_config['User']}@{ssh_config['HostName']}:{ssh_config['Port']}'
        ]
    else:
        error('Something went wrong with the SSH config file or the SSH key, please make sure at least one is valid.')

    if command:
        ssh_argv.append(command)

    subprocess.run(ssh_argv, capture_output=capture_output, input=payload)

def run_paramiko(command: str | None = None, capture_output: bool = False, payload: bytes | None = None) -> bytes | None:
    with get_remote_client().ssh.get_transport().open_session() as channel:
        try:
            channel.get_pty(DEFAULT_TERM, *os.get_terminal_size())
        except OSError:
            channel.get_pty(DEFAULT_TERM, *DEFAULT_PTY_SIZE)

        def resize_pty(signum, frame):
            try:
                channel.resize_pty(*os.get_terminal_size())
            except OSError:
                pass

        signal.signal(signal.SIGWINCH, resize_pty)
        output = b''

        if command:
            channel.exec_command(command)
            if payload:
                channel.sendall(payload)

        else:
            channel.invoke_shell()
            if payload:
                # Wait for initial prompt
                while not output.endswith(b'$ '):
                    if channel.recv_ready():
                        output += channel.recv(BUFFER_SIZE)

                # If the payload contains \n, the channel echoes back the payload with \r\n
                channel.sendall(payload)
                channel.recv(len(payload) + payload.count(b'\n'))
                output = b''

        oldtty = termios.tcgetattr(sys.stdin)
        try:
            if not capture_output:
                success('Connected!')
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            channel.settimeout(0.0)

            while True:
                rlist = select.select([channel, sys.stdin], [], [])[0]
                if channel in rlist:
                    try:
                        buffer = channel.recv(BUFFER_SIZE)
                        if not buffer:
                            break
                        if capture_output:
                            output += buffer
                        else:
                            sys.stdout.buffer.write(buffer)
                            sys.stdout.buffer.flush()
                    except TimeoutError:
                        pass
                if sys.stdin in rlist:
                    buffer = os.read(sys.stdin.fileno(), BUFFER_SIZE)
                    if not buffer:
                        break
                    channel.sendall(buffer)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)

        if capture_output:
            return output

def run_cmd(command: str | None = None, capture_output: bool = False, payload: bytes | None = None, client: str = 'paramiko') -> bytes | None:
    """Run a command on the remote server. If capture_output is True, the standard out bytes are returned."""

    if client == 'local' or 'DOJO_AUTH_TOKEN' in os.environ:
        completed_process = subprocess.run(command or 'bash', shell=True, capture_output=capture_output, input=payload)
        if capture_output:
            return completed_process.stdout
    else:
        if not request('/docker').json().get('success'):
            error('No active challenge session; start a challenge!')

        if client == 'openssh':
            return run_openssh(command, capture_output, payload)
        elif client == 'paramiko':
            return run_paramiko(command, capture_output, payload)
        else:
            error(f'Invalid client: {client}')

def download_file(remote_path: Path, local_path: Path | None = None, log_success: bool = True):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    if not ssh_is_file(remote_path):
        error('Remote path is not a file.')

    if not local_path:
        local_path = Path.cwd()

    local_path = local_path.expanduser().resolve()

    if local_path.is_dir():
        local_path /= remote_path.name

    get_remote_client().sftp.get(str(remote_path), str(local_path))

    if log_success:
        success(f'Downloaded {remote_path} to {local_path}')

def upload_file(local_path: Path, remote_path: Path | None = None, log_success: bool = True):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    local_path = local_path.expanduser().resolve()

    if not local_path.is_file():
        error('Provided path is not a file.')

    if not remote_path:
        remote_path = Path(load_user_config()['ssh']['project_path'])

    if not ssh_is_file(remote_path):
        if ssh_is_dir(remote_path):
            remote_path /= local_path.name
        elif not ssh_is_dir(remote_path.parent):
            ssh_mkdir(remote_path.parent)

    get_remote_client().sftp.put(str(local_path), str(remote_path))

    if log_success:
        success(f'Uploaded {local_path} to {remote_path}')
