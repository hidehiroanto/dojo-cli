"""
Handles SensAI.
"""

from pathlib import Path
import os
import re
from requests import Session
from rich import print as rprint
from rich.markdown import Markdown
from socketio import SimpleClient

from .client import get_remote_client
from .config import load_user_config
from .http import load_cookie, request
from .log import error, fail, info, success
from .remote import run_cmd

def init_sensai():
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    user_config = load_user_config()
    base_url = user_config['base_url']
    cookie_path = Path(user_config['cookie_path']).expanduser().resolve()
    ssh_host = user_config['ssh']['Host']

    if not cookie_path.is_file():
        error('Please login first.')

    cookie_jar = load_cookie(cookie_path)
    if not cookie_jar:
        error('Invalid cookie.')
        return

    headers = {'Cookie': f'session={cookie_jar['session']};'}

    with Session() as session:
        session.get(base_url + '/sensai/', headers=headers)
        headers['Cookie'] += f'sensai_session={session.cookies.get('sensai_session')};'

    with SimpleClient() as sio_client, get_remote_client() as remote_client:
        sio_client.connect(base_url, headers, transports=['websocket'], socketio_path='sensai/socket.io')

        info('Type [bold yellow]! <command>[/] to execute a remote command and add its output to the terminal context.')
        info('Type [bold magenta]@/absolute/path/to/local/file[/] to add a local file to the file context.')
        info(f'Type [bold magenta]@{ssh_host}:/absolute/path/to/remote/file[/] to add a remote file to the file context.')
        info('End every message with a single line containing only [bold cyan]END MESSAGE[/].')
        info('Press [bold cyan]^C[/] to exit SensAI.')

        while True:
            info('Enter message:')
            user_message, terminal_context, file_context = '', '', ''

            user_input = input()
            while user_input != 'END MESSAGE':
                if user_input.startswith('! '):
                    command_input = user_input[2:]
                    command_output = run_cmd(command_input, capture_output=True)
                    if command_output is not None:
                        try:
                            command_output_str = command_output.decode()
                        except UnicodeDecodeError:
                            command_output_str = repr(command_output)
                        finally:
                            success(f'Command output:\n{command_output_str}')
                            terminal_context += f'Command input:\n{command_input}\nCommand output:\n{command_output_str}\n'
                            success('Added command input and output to terminal context.')
                    else:
                        fail('Command failed.')
                    info('Continue message:')
                else:
                    user_message += user_input + '\n'
                user_input = input()

            filenames = re.findall(r'@(\S+)', user_message)
            for filename in filenames:
                if filename.startswith(f'{ssh_host}:'):
                    remote_filename = filename[len(f'{ssh_host}:'):]
                    if remote_client.is_file(remote_filename):
                        try:
                            file_content = remote_client.read_bytes(remote_filename)
                            file_context += f'BEGIN {filename}\n{file_content.decode()}\nEND {filename}\n'
                        except UnicodeDecodeError:
                            file_context += f'BEGIN {filename}\n{file_content}\nEND {filename}\n'
                        except PermissionError:
                            file_context += f'Permission denied: {filename}'
                    else:
                        file_context += f'File not found: {filename}'
                else:
                    if Path(filename).is_file():
                        if os.access(filename, os.R_OK):
                            file_content = Path(filename).read_bytes()
                            try:
                                file_context += f'BEGIN {filename}\n{file_content.decode()}\nEND {filename}\n'
                            except UnicodeDecodeError:
                                file_context += f'BEGIN {filename}\n{file_content}\nEND {filename}\n'
                        else:
                            file_context += f'Permission denied: {filename}'
                    else:
                        file_context += f'File not found: {filename}'

            content = {'message': user_message, 'terminal': terminal_context, 'file': file_context}
            sio_client.emit('new_interaction', {'type': 'learner', 'content': content})
            info('Waiting for SensAI response...')
            assistant_message = sio_client.receive()[1]['content']['message']
            success('SensAI response:')
            rprint(Markdown(assistant_message))
