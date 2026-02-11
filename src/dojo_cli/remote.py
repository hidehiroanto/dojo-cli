"""
Handles remote connections.
"""

import os
from paramiko.client import AutoAddPolicy, SSHClient
from paramiko.sftp_client import SFTPClient
from pathlib import Path
from shutil import which
import stat
import subprocess
import sys

from .config import load_user_config
from .http import request
from .log import error, info, success, warn

def get_ssh_client() -> SSHClient:
    ssh_config = load_user_config()['ssh']

    client = SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(AutoAddPolicy())
    client.connect(
        ssh_config['HostName'],
        ssh_config['Port'],
        ssh_config['User'],
        key_filename=str(Path(ssh_config['IdentityFile']).expanduser())
    )
    return client

def get_sftp_client() -> SFTPClient:
    sftp_client = get_ssh_client().open_sftp()
    sftp_client.chdir(load_user_config()['ssh']['project_path'])
    return sftp_client

def ssh_chmod(path: Path | str, mode: int):
    with get_sftp_client() as sftp_client:
        return sftp_client.chmod(str(path), mode)

def ssh_getsize(path: Path | str) -> int:
    with get_sftp_client() as sftp_client:
        try:
            return sftp_client.stat(str(path)).st_size
        except FileNotFoundError:
            return -1

def ssh_is_dir(path: Path | str) -> bool:
    with get_sftp_client() as sftp_client:
        try:
            return stat.S_ISDIR(sftp_client.stat(str(path)).st_mode)
        except FileNotFoundError:
            return False

def ssh_is_file(path: Path | str) -> bool:
    with get_sftp_client() as sftp_client:
        try:
            return stat.S_ISREG(sftp_client.stat(str(path)).st_mode)
        except FileNotFoundError:
            return False

def ssh_listdir(path: Path | str) -> list[str]:
    with get_sftp_client() as sftp_client:
        return sftp_client.listdir(str(path))

def ssh_mkdir(path: Path | str):
    with get_sftp_client() as sftp_client:
        return sftp_client.mkdir(str(path), 0o755)

def ssh_remove(path: Path | str):
    with get_sftp_client() as sftp_client:
        return sftp_client.remove(str(path))

def ssh_rmdir(path: Path | str):
    with get_sftp_client() as sftp_client:
        return sftp_client.rmdir(str(path))

def ssh_keygen():
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')

    if not Path(which('ssh-keygen') or '/usr/bin/ssh-keygen').is_file():
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

def ssh_run(command: str | None = None, capture_output: bool = False, payload: bytes | None = None) -> bytes | None:
    ssh = Path(which('ssh') or '/usr/bin/ssh')
    if not ssh.is_file():
        error('Please install OpenSSH first.')

    ssh_config = load_user_config()['ssh']
    ssh_config_file = Path(ssh_config['config_file']).expanduser()
    ssh_identity_file = Path(ssh_config['IdentityFile']).expanduser()

    if ssh_config_file.is_file() and f'Host {ssh_config['Host']}' in ssh_config_file.read_text():
        ssh_argv = [ssh, '-F', ssh_config_file, ssh_config['Host']]
    elif ssh_identity_file.is_file() and ssh_identity_file.read_text().startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
        ssh_argv = [
            ssh, '-i', ssh_identity_file,
            '-o', f'ServerAliveCountMax={ssh_config['ServerAliveCountMax']}',
            '-o', f'ServerAliveInterval={ssh_config['ServerAliveInterval']}',
            f'{ssh_config['User']}@{ssh_config['HostName']}:{ssh_config['Port']}'
        ]
    else:
        error('Something went wrong with the SSH config file or the SSH key, please make sure at least one is valid.')

    if command:
        ssh_argv.extend(['-t', command])

    subprocess.run(ssh_argv, capture_output=capture_output, input=payload)

def run_cmd(command: str | None = None, capture_output: bool = False, payload: bytes | None = None, client: str = 'paramiko') -> bytes | None:
    """Run a command on the remote server. If capture_output is True, the stdout bytes are returned."""

    if 'DOJO_AUTH_TOKEN' in os.environ:
        return subprocess.run(command or 'bash', shell=True, capture_output=capture_output, input=payload).stdout

    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    if client == 'paramiko':
        with get_ssh_client() as client:
            stdin, stdout, stderr = client.exec_command(command or 'bash', get_pty=True)
            if payload:
                stdin.write(payload)
                stdin.channel.shutdown_write()
            while not stdout.channel.exit_status_ready():
                pass
            if capture_output:
                return stdout.read()
            else:
                sys.stdout.buffer.write(stdout.read())

    elif client == 'openssh':
        return ssh_run(command, capture_output, payload)

def transfer(src_path: Path | str, dst_path: Path | str, upload: bool = False):
    if 'DOJO_AUTH_TOKEN' in os.environ:
        error('Please run this locally instead of on the dojo.')
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    with get_sftp_client() as sftp_client:
        getattr(sftp_client, 'put' if upload else 'get')(str(src_path), str(dst_path))
