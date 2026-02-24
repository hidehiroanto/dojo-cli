"""
Handles SensAI.
"""

import os
from pathlib import Path
import re
from requests import Session
from rich import print as rprint
from rich.markdown import Markdown as RichMarkdown
import shlex
from socketio import SimpleClient

from textual.app import App, ComposeResult
from textual.containers import HorizontalGroup, VerticalScroll
from textual.events import Key
from textual.widgets import Button, Footer, Input, Markdown, OptionList

from .client import get_remote_client
from .config import load_user_config
from .http import load_cookie, request
from .log import error, fail, info, success, warn
from .remote import run_cmd

WELCOME_BANNER = r'''
```
__        __   _                            _          ____  _____ _   _ ____    _    ___
\ \      / /__| | ___ ___  _ __ ___   ___  | |_ ___   / ___|| ____| \ | / ___|  / \  |_ _|
 \ \ /\ / / _ \ |/ __/ _ \| '_ ` _ \ / _ \ | __/ _ \  \___ \|  _| |  \| \___ \ / _ \  | |
  \ V  V /  __/ | (_| (_) | | | | | |  __/ | || (_) |  ___) | |___| |\  |___) / ___ \ | |
   \_/\_/ \___|_|\___\___/|_| |_| |_|\___|  \__\___/  |____/|_____|_| \_|____/_/   \_\___|
```
'''

INSTRUCTIONS = r'''
- Type `!<command>` to execute a remote command and add its output to the terminal context.
- Type `@<path/to/file>` to add the contents of a file to the file context.
- Type `/h` or `/help` to display this help message again.
- Type `/w` or `/welcome` to display the welcome banner again.
- Type any of these to quit: `/exit`, `/q`, `/quit`
'''

def show_welcome(app: App, *argv):
    app.query_one(VerticalScroll).mount(Markdown(WELCOME_BANNER))

def show_instructions(app: App, *argv):
    app.query_one(VerticalScroll).mount(Markdown(INSTRUCTIONS))

def exit_app(app: App, *argv):
    app.exit()

SLASH_COMMANDS = {
    'exit': exit_app,
    'h': show_instructions,
    'help': show_instructions,
    'q': exit_app,
    'quit': exit_app,
    'w': show_welcome,
    'welcome': show_welcome,
}

class SensaiApp(App):
    CSS = """
    VerticalScroll {
        margin: 1;
    }

    HorizontalGroup {
        margin: 1;
    }

    Input {
        width: 1fr;
    }

    OptionList {
        margin: 1;
        height: 10;
    }
    """

    MAX_OPTIONS = 20
    HEIGHT_DIFF_THRESHOLD = 6

    def __init__(self, base_url: str, session_cookie: str):
        super().__init__()
        self.base_url = base_url
        self.session_cookie = session_cookie

        self.user_message, self.terminal_context, self.file_context = '', '', ''

        self.command_history = []
        self.command_history_index = 0
        self.file_query = ''
        self.shell_commands = []
        self.option_cache = {}

        session = Session()
        session.cookies.set('session', self.session_cookie)
        session.get(self.base_url + '/sensai/')

        self.sio = SimpleClient(http_session=session)
        self.sio.connect(self.base_url, transports=['websocket'], socketio_path='sensai/socket.io')
        self.remote_client = get_remote_client()

    def compose(self) -> ComposeResult:
        yield VerticalScroll()
        with HorizontalGroup():
            yield Input(placeholder='Enter message', select_on_focus=False)
            yield Button('Send')
        yield OptionList()
        yield Footer()

    def start_app(self):
        show_welcome(self)
        show_instructions(self)
        self.query_one(Input).focus()
        self.query_one(OptionList).display = False

    def on_mount(self):
        self.call_after_refresh(self.start_app)

    def add_file_context(self, filenames: list[str]):
        for filename in filenames:
            if self.remote_client.is_file(filename):
                try:
                    file_content = self.remote_client.read_bytes(filename)
                    self.file_context += f'BEGIN {filename}\n{file_content.decode()}\nEND {filename}\n'
                except UnicodeDecodeError:
                    self.file_context += f'BEGIN {filename}\n{file_content}\nEND {filename}\n'
                except PermissionError:
                    self.file_context += f'Permission denied: {filename}'
            elif Path(filename).expanduser().is_file():
                if os.access(filename, os.R_OK):
                    file_content = Path(filename).read_bytes()
                    try:
                        self.file_context += f'BEGIN {filename}\n{file_content.decode()}\nEND {filename}\n'
                    except UnicodeDecodeError:
                        self.file_context += f'BEGIN {filename}\n{file_content}\nEND {filename}\n'
                else:
                    self.file_context += f'Permission denied: {filename}'
            else:
                self.file_context += f'File not found: {filename}'

    async def run_shell_cmd(self):
        vertical_scroll = self.query_one(VerticalScroll)
        command_fds = self.remote_client.ssh.exec_command(self.user_message[1:].strip())
        self.user_message = ''
        command_stdout, command_stderr = command_fds[1].read(), command_fds[2].read()

        if command_stdout:
            command_stdout_str = command_stdout.decode(errors='replace')
            if '````' in command_stdout_str:
                command_stdout_md = f'**Command stdout:**\n{command_stdout_str}\n'
            elif '```' in command_stdout_str:
                command_stdout_md = f'**Command stdout:**\n````\n{command_stdout_str}\n````\n'
            else:
                command_stdout_md = f'**Command stdout:**\n```\n{command_stdout_str}\n```\n'
            self.terminal_context += command_stdout_md
            await vertical_scroll.mount(Markdown(command_stdout_md))

        if command_stderr:
            command_stderr_str = command_stderr.decode(errors='replace')
            if '````' in command_stderr_str:
                command_stderr_md = f'**Command stderr:**\n{command_stderr_str}\n'
            elif '```' in command_stderr_str:
                command_stderr_md = f'**Command stderr:**\n````\n{command_stderr_str}\n````\n'
            else:
                command_stderr_md = f'**Command stderr:**\n```\n{command_stderr_str}\n```\n'
            self.terminal_context += command_stderr_md
            await vertical_scroll.mount(Markdown(command_stderr_md))

        vertical_scroll.scroll_end()
        self.query_one(Button).disabled = False
        input_box = self.query_one(Input)
        input_box.disabled = False
        input_box.placeholder = 'Enter message'
        input_box.focus()

    async def emit_and_receive_event(self):
        self.add_file_context(re.findall(r'@(\S+)', self.user_message))
        content = {'message': self.user_message, 'terminal': self.terminal_context, 'file': self.file_context}
        self.sio.emit('new_interaction', {'type': 'learner', 'content': content})
        self.user_message, self.terminal_context, self.file_context = '', '', ''

        event = self.sio.receive()
        if event[0] == 'new_interaction':
            assistant_message = event[1]['content']['message']
        elif event[0] == 'user_rate_limit':
            remaining = max([limit['remaining'] for limit in event[1] if limit['remaining'] is not None] + [0])
            assistant_message = f'User rate limit: Please wait {remaining} seconds before sending your message.'
        else:
            assistant_message = f'Unknown event: {event}'

        vertical_scroll = self.query_one(VerticalScroll)
        await vertical_scroll.mount(Markdown(f'**SensAI:** {assistant_message}'))
        vertical_scroll.scroll_end()

        self.query_one(Button).disabled = False
        input_box = self.query_one(Input)
        input_box.disabled = False
        input_box.placeholder = 'Enter message'
        input_box.focus()

    async def submit_input(self, input_box: Input):
        if self.user_message:
            input_box.clear()
            vertical_scroll = self.query_one(VerticalScroll)
            option_list = self.query_one(OptionList)
            option_list.clear_options()
            option_list.display = False

            self.command_history.append(self.user_message)
            self.command_history_index = len(self.command_history)
            self.file_query = ''
            self.shell_commands = []
            self.option_cache = {}

            if re.match(r'/\S+', self.user_message):
                command_argv = shlex.split(self.user_message)
                command = command_argv[0][1:]
                if command in SLASH_COMMANDS:
                    SLASH_COMMANDS[command](self, *command_argv[1:])
                else:
                    await vertical_scroll.mount(Markdown(f'**Unknown command:** `{self.user_message}`'))
                vertical_scroll.scroll_end()

            elif self.user_message.startswith('!'):
                if '````' in self.user_message:
                    command_md = f'**Command:** {self.user_message[1:].strip()}\n'
                elif '```' in self.user_message:
                    command_md = f'**Command:** ```` {self.user_message[1:].strip()} ````\n'
                elif '``' in self.user_message:
                    command_md = f'**Command:** ``` {self.user_message[1:].strip()} ```\n'
                elif '`' in self.user_message:
                    command_md = f'**Command:** `` {self.user_message[1:].strip()} ``\n'
                else:
                    command_md = f'**Command:** ` {self.user_message[1:].strip()} `\n'
                self.terminal_context += command_md
                await vertical_scroll.mount(Markdown(command_md))

                self.query_one(Button).disabled = True
                input_box.disabled = True
                input_box.placeholder = 'Waiting...'
                if vertical_scroll.virtual_size.height - vertical_scroll.scrollable_size.height > self.HEIGHT_DIFF_THRESHOLD:
                    vertical_scroll.scroll_end(on_complete=self.run_shell_cmd)
                else:
                    self.call_after_refresh(self.run_shell_cmd)

            else:
                await vertical_scroll.mount(Markdown(f'**You:** {re.sub(r'@(\S+)', r'`@\1`', self.user_message)}'))
                self.query_one(Button).disabled = True
                input_box.disabled = True
                input_box.placeholder = 'Waiting...'
                if vertical_scroll.virtual_size.height - vertical_scroll.scrollable_size.height > self.HEIGHT_DIFF_THRESHOLD:
                    vertical_scroll.scroll_end(on_complete=self.emit_and_receive_event)
                else:
                    self.call_after_refresh(self.emit_and_receive_event)

    def update_option_list(self):
        input_box = self.query_one(Input)
        option_list = self.query_one(OptionList)
        option_list.clear_options()

        if input_box.value.startswith('/'):
            option_list.add_options([f'/{cmd}' for cmd in SLASH_COMMANDS if cmd.startswith(input_box.value[1:])])
            self.file_query = ''
            option_list.display = True
            return

        elif input_box.value.startswith('!'):
            if not self.shell_commands:
                for path_dir in self.remote_client.ssh.exec_command('echo $PATH')[1].read().decode().split(':'):
                    self.shell_commands += self.remote_client.listdir(path_dir)
                self.shell_commands = sorted(set(self.shell_commands))
            option_list.add_options([f'!{cmd}' for cmd in self.shell_commands if cmd.startswith(input_box.value[1:])])
            self.file_query = ''
            option_list.display = True
            return

        for span in list(match.span() for match in re.finditer(r'@\S{3,}', input_box.value)):
            if span[0] <= input_box.cursor_position <= span[1]:
                self.file_query = input_box.value[span[0] + 1:span[1]].casefold()
                break
        else:
            self.file_query = ''
            option_list.display = False
            return

        if self.file_query not in self.option_cache:
            fd_argv = ['fd', '-apu', '-t', 'f', '.', '/challenge', '/home', '/tmp']
            fzf_argv = ['fzf', '-f', self.file_query]
            head_argv = ['head', '-n', str(self.MAX_OPTIONS)]
            command = ' | '.join(map(shlex.join, [fd_argv, fzf_argv, head_argv]))
            self.option_cache[self.file_query] = self.remote_client.ssh.exec_command(command)[1].read().decode().splitlines()

        if self.option_cache[self.file_query]:
            option_list.add_options(self.option_cache[self.file_query])
            option_list.highlighted = 0
            option_list.display = True
        else:
            self.file_query = ''
            option_list.display = False

    def on_input_changed(self, event: Input.Changed):
        self.update_option_list()

    def select_option(self):
        input_box = self.query_one(Input)
        option_list = self.query_one(OptionList)
        input_box.focus()

        if input_box.value.startswith('/') or input_box.value.startswith('!'):
            input_box.value = self.user_message
            input_box.action_end()
        else:
            input_box.cursor_position = input_box.value.index(f'@{self.file_query}')
            input_box.value = input_box.value.replace(f'@{self.file_query}', f'@{self.user_message}')
            self.file_query = ''
            option_list.clear_options()
            option_list.display = False
            input_box.action_cursor_right_word()

    def on_key(self, event: Key):
        input_box = self.query_one(Input)
        option_list = self.query_one(OptionList)
        if event.key == 'down':
            if input_box.has_focus and self.command_history_index < len(self.command_history):
                self.command_history_index += 1
                if self.command_history_index == len(self.command_history):
                    input_box.value = self.user_message
                else:
                    input_box.value = self.command_history[self.command_history_index]
            elif input_box.has_focus and option_list.options:
                option_list.focus()
                option_list.highlighted = 0 if event.key == 'down' else len(option_list.options) - 1
                event.stop()
                event.prevent_default()
        elif event.key == 'up':
            if input_box.has_focus and self.command_history_index > 0:
                if self.command_history_index == len(self.command_history):
                    self.user_message = input_box.value
                self.command_history_index -= 1
                input_box.value = self.command_history[self.command_history_index]
            elif option_list.has_focus and option_list.highlighted == 0:
                input_box.focus()
                event.stop()
                event.prevent_default()
        elif event.key in ['left', 'right'] and input_box.has_focus:
            self.call_after_refresh(self.update_option_list)
        elif event.key == 'tab' and option_list.has_focus and option_list.highlighted_option:
            self.user_message = str(option_list.highlighted_option.prompt)
            self.call_after_refresh(self.select_option)
            event.stop()
            event.prevent_default()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self.user_message = str(event.option.prompt)
        self.call_after_refresh(self.select_option)

    async def on_input_submitted(self, event: Input.Submitted):
        self.user_message = event.value
        await self.submit_input(event.input)

    async def on_button_pressed(self, event: Button.Pressed):
        input_box = self.query_one(Input)
        self.user_message = input_box.value
        await self.submit_input(input_box)

def run_simple(base_url: str, session_cookie: str):
    with Session() as session:
        session.cookies.set('session', session_cookie)
        session.get(base_url + '/sensai/')
        with SimpleClient(http_session=session) as sio, get_remote_client() as remote_client:
            sio.connect(base_url, transports=['websocket'], socketio_path='sensai/socket.io')
            rprint(RichMarkdown(WELCOME_BANNER + INSTRUCTIONS))
            terminal_context, file_context = '', ''

            while True:
                info('[b]Enter message:[/] ', end='', flush=True)

                user_message = input()
                while user_message.endswith('\\'):
                    user_message = user_message[:-1] + input()

                if user_message.startswith('/'):
                    command = user_message[1:]
                    if command in ['exit', 'q', 'quit']:
                        break
                    elif command in ['h', 'help']:
                        rprint(RichMarkdown(INSTRUCTIONS))
                    elif command in ['w', 'welcome']:
                        rprint(RichMarkdown(WELCOME_BANNER))
                    else:
                        fail('Unknown command')

                elif user_message.startswith('!'):
                    command_in = user_message[1:]
                    command_out = run_cmd(command_in, capture_output=True, pty=False)
                    if command_out is not None:
                        command_out_str = command_out.decode(errors='replace')
                        command_out_md = command_out_str if '```' in command_out_str else f'```\n{command_out_str}\n```'
                        rprint(RichMarkdown(f'**Command output:**\n{command_out_md}'))
                        terminal_context += f'Command input:\n{command_in}\nCommand output:\n{command_out_md}\n'
                        success('Added command input and output to terminal context.')
                    else:
                        fail('Command failed.')

                elif user_message.strip():
                    filenames = re.findall(r'@(\S+)', user_message)
                    for filename in filenames:
                        if remote_client.is_file(filename):
                            try:
                                file_content = remote_client.read_bytes(filename)
                                file_context += f'BEGIN {filename}\n{file_content.decode()}\nEND {filename}\n'
                            except UnicodeDecodeError:
                                file_context += f'BEGIN {filename}\n{file_content}\nEND {filename}\n'
                            except PermissionError:
                                file_context += f'Permission denied: {filename}'
                        elif Path(filename).expanduser().is_file():
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
                    sio.emit('new_interaction', {'type': 'learner', 'content': content})
                    terminal_context, file_context = '', ''
                    info('Waiting for SensAI response...')

                    event = sio.receive()
                    if event[0] == 'new_interaction':
                        success('SensAI response:')
                        rprint(RichMarkdown(event[1]['content']['message']))
                    elif event[0] == 'user_rate_limit':
                        remaining = max([limit['remaining'] for limit in event[1] if limit['remaining'] is not None] + [0])
                        fail('SensAI response:')
                        rprint(RichMarkdown(f'User rate limit: Please wait {remaining} seconds before sending your message.'))
                    else:
                        warn('SensAI response:')
                        rprint(RichMarkdown(f'Unknown event: {event}'))

def init_sensai(simple: bool = False):
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    user_config = load_user_config()
    base_url = user_config['base_url']
    cookie_path = Path(user_config['cookie_path']).expanduser().resolve()

    if not cookie_path.is_file():
        error('Please login first.')

    cookie_jar = load_cookie(cookie_path)
    if not isinstance(cookie_jar, dict) or not cookie_jar.get('session'):
        error('Invalid cookie.')
        return

    if simple:
        run_simple(base_url, cookie_jar['session'])
    else:
        app = SensaiApp(base_url, cookie_jar['session'])
        app.run()
