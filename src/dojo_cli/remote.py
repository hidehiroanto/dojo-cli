"""
Handles remote SSH connections.
"""

import os
from paramiko.client import AutoAddPolicy, SSHClient
from paramiko.sftp_client import SFTPClient
from pathlib import Path
import select
from shutil import which
import signal
import stat
import subprocess
import sys
import termios
import tty

from .config import load_user_config
from .http import request
from .log import error, info, success, warn
from .terminal import apply_style

ssh_client = None

def get_ssh_client() -> SSHClient:
    ssh_config = load_user_config()['ssh']

    global ssh_client
    if not ssh_client:
        ssh_client = SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(AutoAddPolicy())
        ssh_client.connect(
            ssh_config['HostName'],
            ssh_config['Port'],
            ssh_config['User'],
            key_filename=str(Path(ssh_config['IdentityFile']).expanduser())
        )
    return ssh_client

def get_sftp_client() -> SFTPClient:
    sftp_client = get_ssh_client().open_sftp()
    sftp_client.chdir(load_user_config()['ssh']['project_path'])
    return sftp_client

def ssh_chmod(path: Path | str, mode: int):
    with get_sftp_client() as sftp_client:
        sftp_client.chmod(str(path), mode)

def ssh_getsize(path: Path | str) -> int:
    stat_result = ssh_stat(path)
    if not stat_result:
        return -1
    return stat_result.st_size

def ssh_is_dir(path: Path | str) -> bool:
    stat_result = ssh_stat(path)
    if not stat_result:
        return False
    return stat.S_ISDIR(stat_result.st_mode)

def ssh_is_file(path: Path | str) -> bool:
    stat_result = ssh_stat(path)
    if not stat_result:
        return False
    return stat.S_ISREG(stat_result.st_mode)

def ssh_listdir(path: Path | str) -> list[str]:
    with get_sftp_client() as sftp_client:
        return sftp_client.listdir(str(path))

def ssh_mkdir(path: Path | str):
    with get_sftp_client() as sftp_client:
        for parent in Path(path).parents[::-1]:
            if not ssh_is_dir(parent):
                sftp_client.mkdir(str(parent), 0o755)
        if not ssh_is_dir(path):
            sftp_client.mkdir(str(path), 0o755)

def ssh_open(path: Path | str, mode: str = 'r'):
    return get_sftp_client().open(str(path), mode)

def ssh_remove(path: Path | str):
    with get_sftp_client() as sftp_client:
        sftp_client.remove(str(path))

def ssh_rmdir(path: Path | str):
    with get_sftp_client() as sftp_client:
        for child in sftp_client.listdir(str(path)):
            child_path = Path(path) / child
            if ssh_is_dir(child_path):
                ssh_rmdir(child_path)
            else:
                sftp_client.remove(str(child_path))
        sftp_client.rmdir(str(path))

def ssh_stat(path: Path | str) -> os.stat_result | None:
    with get_sftp_client() as sftp_client:
        try:
            return sftp_client.stat(str(path))
        except FileNotFoundError:
            return None

def ssh_keygen():
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')

    ssh_keygen = Path(which('ssh-keygen') or '/usr/bin/ssh-keygen')
    if not ssh_keygen.is_file():
        error('Please install ssh-keygen first.')

    user_config = load_user_config()
    ssh_config = user_config['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

    if ssh_identity_file.is_file():
        warn(f'Identity file already exists at {ssh_identity_file}, override?')
        if input('(y/N) > ').strip()[0].lower() != 'y':
            warn('Aborting SSH key generation!')
            return

    subprocess.run([ssh_keygen, '-N', '', '-f', ssh_identity_file, '-t', ssh_config['algorithm']])

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

def print_file(path: Path):
    if ssh_is_dir(path):
        error(f'{apply_style(path)} is a directory.')
    elif not ssh_is_file(path):
        error(f'{apply_style(path)} is not an existing file.')

    try:
        with get_sftp_client() as sftp_client:
            with sftp_client.open(str(path), 'rb') as f:
                sys.stdout.buffer.write(f.read())
                sys.stdout.buffer.flush()
    except PermissionError:
        error(f'Permission to read {apply_style(path)} denied.')

def run_openssh(command: str | None = None, capture_output: bool = False, payload: bytes | None = None) -> bytes | None:
    ssh = Path(which('ssh') or '/usr/bin/ssh')
    if not ssh.is_file():
        error('Please install OpenSSH first.')

    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

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
    with get_ssh_client().get_transport().open_session() as channel:
        try:
            width, height = os.get_terminal_size()
        except OSError:
            width, height = 80, 24
        channel.get_pty('xterm-256color', width, height)

        if command:
            channel.exec_command(command)
            with channel.makefile_stdin('wb') as stdin:
                if payload:
                    stdin.write(payload)
            with channel.makefile('rb') as stdout, channel.makefile_stderr('rb') as stderr:
                output, err = stdout.read(), stderr.read()
            sys.stderr.buffer.write(err)
            sys.stderr.buffer.flush()
            if capture_output:
                return output
            else:
                sys.stdout.buffer.write(output)
                sys.stdout.buffer.flush()
        else:
            channel.invoke_shell()
            if payload:
                # wait for initial prompt
                buffer = b''
                while not buffer.endswith(b'$ '):
                    if channel.recv_ready():
                        buffer += channel.recv(1024)

                channel.send(payload)
                # If the payload contains \n, the channel sends back \r\n
                channel.recv(len(payload) + payload.count(b'\n'))

            def resize_pty(signum, frame):
                try:
                    width, height = os.get_terminal_size()
                    channel.resize_pty(width, height)
                except OSError:
                    pass

            signal.signal(signal.SIGWINCH, resize_pty)
            oldtty = termios.tcgetattr(sys.stdin)
            output = b''
            try:
                tty.setraw(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
                channel.settimeout(0.0)
                while True:
                    rlist = select.select([channel, sys.stdin], [], [])[0]
                    if channel in rlist:
                        try:
                            data = channel.recv(1024)
                            if not data:
                                break
                            if capture_output:
                                output += data
                            else:
                                sys.stdout.buffer.write(data)
                                sys.stdout.buffer.flush()
                        except TimeoutError:
                            pass
                    if sys.stdin in rlist:
                        data = os.read(sys.stdin.fileno(), 1024)
                        if not data:
                            break
                        channel.send(data)
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)

            if capture_output:
                return output

def run_cmd(command: str | None = None, capture_output: bool = False, payload: bytes | None = None, client: str = 'paramiko') -> bytes | None:
    """Run a command on the remote server. If capture_output is True, the stdout bytes are returned."""

    if client == 'local' or 'DOJO_AUTH_TOKEN' in os.environ:
        return subprocess.run(command or 'bash', shell=True, capture_output=capture_output, input=payload).stdout
    else:
        if not request('/docker').json().get('success'):
            error('No active challenge session; start a challenge!')

        if client == 'openssh':
            return run_openssh(command, capture_output, payload)
        elif client == 'paramiko':
            return run_paramiko(command, capture_output, payload)
        else:
            error(f'Invalid client: {client}')

def transfer(src_path: Path | str, dst_path: Path | str, upload: bool = False):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    with get_sftp_client() as sftp_client:
        getattr(sftp_client, 'put' if upload else 'get')(str(src_path), str(dst_path))
