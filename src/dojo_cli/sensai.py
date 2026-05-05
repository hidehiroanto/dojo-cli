"""Handles SensAI."""

from collections import OrderedDict
import os
from pathlib import Path
import re
import shlex
import socket
from threading import Lock
from time import monotonic
from typing import Optional

from niquests import Session
from niquests.cookies import create_cookie
from rich import print as rprint
from rich.markdown import Markdown as RichMarkdown
from socketio import SimpleClient

from textual.app import App, ComposeResult
from textual.containers import HorizontalGroup, VerticalScroll
from textual.events import Key
from textual.timer import Timer
from textual.widgets import Button, Footer, Input, Markdown, OptionList

from .client import get_remote_client
from .config import load_user_config
from .http import load_cookie, request
from .log import error, fail, info, success, warn
from .remote import run_cmd
from .socketio_niquests import SocketIoSession, SocketIoSimpleClient, close_socketio_client

WELCOME_BANNER = r'''```
__        __   _                            _
\ \      / /__| | ___ ___  _ __ ___   ___  | |_ ___
 \ \ /\ / / _ \ |/ __/ _ \| '_ ` _ \ / _ \ | __/ _ \
  \ V  V /  __/ | (_| (_) | | | | | |  __/ | || (_) |
   \_/\_/ \___|_|\___\___/|_| |_| |_|\___|  \__\___/

    ███████╗███████╗███╗   ██╗███████╗ █████╗ ██╗
    ██╔════╝██╔════╝████╗  ██║██╔════╝██╔══██╗██║
    ███████╗█████╗  ██╔██╗ ██║███████╗███████║██║
    ╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══██║██║
    ███████║███████╗██║ ╚████║███████║██║  ██║██║
    ╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚═╝
```'''

INSTRUCTIONS = r'''
- Type `!<command>` to execute a remote command and add its output to the terminal context.
- Type `@<path/to/file>` to add the contents of a file to the file context.
- Type `/h` or `/help` to display this help message again.
- Type `/w` or `/welcome` to display the welcome banner again.
- Type any of these to quit: `/exit`, `/q`, `/quit`
'''

DEFAULT_SENSAI_TIMEOUT = 60.0

SLASH_COMMANDS = {
    'exit': lambda app, *argv: app.exit(),
    'h': lambda app, *argv: app.query_one(VerticalScroll).mount(Markdown(INSTRUCTIONS)),
    'help': lambda app, *argv: app.query_one(VerticalScroll).mount(Markdown(INSTRUCTIONS)),
    'q': lambda app, *argv: app.exit(),
    'quit': lambda app, *argv: app.exit(),
    'w': lambda app, *argv: app.query_one(VerticalScroll).mount(Markdown(WELCOME_BANNER)),
    'welcome': lambda app, *argv: app.query_one(VerticalScroll).mount(Markdown(WELCOME_BANNER)),
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
    FILE_OPTION_CACHE_RESULT_SIZE = 200
    FILE_OPTION_CACHE_MIN_RESULTS = 5
    FILE_OPTION_CACHE_SIZE = 64
    FILE_OPTION_CACHE_TTL = 30.0
    FILE_OPTION_FETCH_TIMEOUT = 30.0
    OPTION_UPDATE_DELAY = 0.15
    PATH_MATCH_BOUNDARIES = frozenset('/._- ')

    def __init__(self, base_url: str, session_cookie: str, timeout: Optional[float]):
        super().__init__()
        self.base_url = base_url
        self.session_cookie = session_cookie
        self.timeout = timeout

        self.http_session: Optional[SocketIoSession] = None
        self.sio: Optional[SocketIoSimpleClient] = None
        self.user_message, self.terminal_context, self.file_context = '', '', ''

        self.command_history = []
        self.command_history_index = 0
        self.shell_commands = []
        self.option_cache: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()
        self.option_fetches: set[str] = set()
        self.option_fetch_lock = Lock()
        self.option_update_timer: Optional[Timer] = None
        self.remote_client = get_remote_client()

    def compose(self) -> ComposeResult:
        yield VerticalScroll()
        with HorizontalGroup():
            yield Input(placeholder='Enter message', select_on_focus=False)
            yield Button('Send')
        yield OptionList()
        yield Footer()

    def start_app(self):
        self.query_one(VerticalScroll).mount(Markdown(WELCOME_BANNER))
        self.query_one(VerticalScroll).mount(Markdown(INSTRUCTIONS))
        self.restore_input()
        self.query_one(OptionList).display = False

    def restore_input(self):
        input_box = self.query_one(Input)
        input_box.disabled = False
        input_box.placeholder = 'Enter message'
        self.set_focus(input_box, scroll_visible=False)
        self.query_one(Button).disabled = False

    async def connect_sensai(self):
        self.http_session = SocketIoSession(self.session_cookie)
        try:
            response = await self.http_session.get(self.base_url + '/sensai/')
            await response.read()
            await response.close()
            self.sio = SocketIoSimpleClient(http_session=self.http_session)
            await self.sio.connect(self.base_url, transports=['websocket'], socketio_path='sensai/socket.io')
        except Exception:
            await self.disconnect_sensai()
            raise

    async def disconnect_sensai(self):
        await close_socketio_client(self.sio, self.http_session)
        self.sio = None
        self.http_session = None

    async def on_mount(self) -> None:
        input_box = self.query_one(Input)
        input_box.disabled = True
        input_box.placeholder = 'Connecting to SensAI...'
        self.query_one(Button).disabled = True

        try:
            await self.connect_sensai()
        except Exception as exc:
            self.exit(return_code=1, message=RichMarkdown(f'**Failed to connect to SensAI:** `{exc}`'))
            return

        self.call_after_refresh(self.start_app)

    async def on_unmount(self) -> None:
        self.cancel_option_update_timer()
        await self.disconnect_sensai()

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
        if self.sio is None:
            self.restore_input()
            return

        vertical_scroll = self.query_one(VerticalScroll)
        try:
            self.add_file_context(re.findall(r'@(\S+)', self.user_message))
            content = {'message': self.user_message, 'terminal': self.terminal_context, 'file': self.file_context}
            await self.sio.emit('new_interaction', {'type': 'learner', 'content': content})
            self.user_message, self.terminal_context, self.file_context = '', '', ''

            event = await self.sio.receive(timeout=self.timeout)
            if event[0] == 'new_interaction':
                assistant_message = event[1]['content']['message']
            elif event[0] == 'user_rate_limit':
                remaining = max([limit['remaining'] for limit in event[1] if limit['remaining'] is not None] + [0])
                assistant_message = f'User rate limit: Please wait {remaining} seconds before sending your message.'
            else:
                assistant_message = f'Unknown event: {event}'

            await vertical_scroll.mount(Markdown(f'**SensAI:** {assistant_message}'))
        except TimeoutError:
            timeout_message = 'No response received.' if self.timeout is None else f'No response after {self.timeout:g} seconds.'
            await vertical_scroll.mount(Markdown(f'**SensAI timeout:** {timeout_message}'))
        except Exception as exc:
            await vertical_scroll.mount(Markdown(f'**SensAI connection error:** `{exc}`'))
        finally:
            vertical_scroll.scroll_end()
            self.restore_input()

    async def submit_input(self, input_box: Input):
        if self.user_message:
            self.cancel_option_update_timer()
            input_box.clear()
            vertical_scroll = self.query_one(VerticalScroll)
            option_list = self.query_one(OptionList)
            option_list.clear_options()
            option_list.display = False

            self.command_history.append(self.user_message)
            self.command_history_index = len(self.command_history)

            if re.match(r'/\S+', self.user_message):
                command_args = shlex.split(self.user_message)
                command = command_args[0][1:]
                if command in SLASH_COMMANDS:
                    SLASH_COMMANDS[command](self, *command_args[1:])
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
                self.set_focus(vertical_scroll, scroll_visible=False)
                vertical_scroll.call_after_refresh(
                    lambda: vertical_scroll.scroll_to(
                        y=vertical_scroll.max_scroll_y,
                        animate=True,
                    )
                )
                self.call_after_refresh(
                    lambda: self.run_worker(
                        self.run_shell_cmd(),
                        name='sensai-shell',
                        group='sensai-shell',
                        exclusive=True,
                        exit_on_error=False,
                    )
                )

            else:
                await vertical_scroll.mount(Markdown(f'**You:** {re.sub(r'@(\S+)', r'`@\1`', self.user_message)}'))
                self.query_one(Button).disabled = True
                input_box.disabled = True
                input_box.placeholder = 'Waiting...' if self.timeout is None else f'Waiting up to {self.timeout:g}s...'
                self.set_focus(vertical_scroll, scroll_visible=False)
                vertical_scroll.call_after_refresh(
                    lambda: vertical_scroll.scroll_to(
                        y=vertical_scroll.max_scroll_y,
                        animate=True,
                    )
                )
                self.call_after_refresh(
                    lambda: self.run_worker(
                        self.emit_and_receive_event(),
                        name='sensai-response',
                        group='sensai-response',
                        exclusive=True,
                        exit_on_error=False,
                    )
                )

    def get_file_query_at_cursor(self, value: str, cursor_position: int) -> Optional[str]:
        for match in re.finditer(r'@\S{3,}', value):
            span = match.span()
            if span[0] <= cursor_position <= span[1]:
                return value[span[0] + 1:span[1]].casefold()
        return None

    def show_option_list(self, new_options: list[str]):
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        option_list.display = False
        if new_options:
            option_list.add_options(new_options)
            option_list.display = True
            option_list.highlighted = 0

    def update_option_list(self):
        input_box = self.query_one(Input)
        self.show_option_list([])
        new_options = []

        if input_box.value.startswith('/'):
            for cmd in SLASH_COMMANDS:
                if cmd.startswith(input_box.value[1:]):
                    new_options.append(f'/{cmd}')

        elif input_box.value.startswith('!'):
            if not self.shell_commands:
                path_dirs = self.remote_client.ssh.exec_command('echo $PATH')[1].read().decode().split(':')
                fd_args = ['fd', '-Lapu', '-tx', '.'] + path_dirs
                command_stdout = self.remote_client.ssh.exec_command(shlex.join(fd_args))[1].read()
                self.shell_commands = sorted(set(Path(p).name for p in command_stdout.decode().splitlines()))

            for cmd in self.shell_commands:
                if cmd.startswith(input_box.value[1:]):
                    new_options.append(f'!{cmd}')

        else:
            file_query_casefold = self.get_file_query_at_cursor(input_box.value, input_box.cursor_position)
            if file_query_casefold is None:
                return

            new_options = self.get_cached_file_options(file_query_casefold, require_min_results=False)
            if new_options is None:
                self.request_file_options(file_query_casefold)
                return
            if len(new_options) < self.FILE_OPTION_CACHE_MIN_RESULTS:
                self.request_file_options(file_query_casefold)

        self.show_option_list(new_options)

    def is_file_option_cache_fresh(self, cached_at: float) -> bool:
        return monotonic() - cached_at <= self.FILE_OPTION_CACHE_TTL

    def get_fuzzy_match_positions(self, query: str, candidate: str) -> Optional[list[int]]:
        positions = []
        start = 0
        for char in query:
            position = candidate.find(char, start)
            if position < 0:
                return None
            positions.append(position)
            start = position + 1
        return positions

    def is_fuzzy_match(self, query: str, candidate: str) -> bool:
        return self.get_fuzzy_match_positions(query, candidate.casefold()) is not None

    def get_file_option_rank(self, query: str, option: str) -> Optional[tuple[int, int, int, int, int, int, int, int]]:
        option_casefold = option.casefold()
        positions = self.get_fuzzy_match_positions(query, option_casefold)
        if positions is None:
            return None

        query_basename = query.rsplit('/', 1)[-1]
        option_basename = option_casefold.rsplit('/', 1)[-1]
        substring_position = option_casefold.find(query)
        basename_substring_position = option_basename.find(query_basename) if query_basename else -1
        contiguous_position = min(
            (
                position for position in [substring_position, basename_substring_position]
                if position >= 0
            ),
            default=-1,
        )
        boundary_matches = sum(
            1 for position in positions
            if position == 0 or option_casefold[position - 1] in self.PATH_MATCH_BOUNDARIES
        )

        return (
            int(not option_casefold.startswith(query)),
            int(not (query_basename and option_basename.startswith(query_basename))),
            int(contiguous_position < 0),
            -boundary_matches,
            contiguous_position if contiguous_position >= 0 else positions[0],
            positions[-1] - positions[0],
            len(option_casefold),
            positions[0],
        )

    def get_ranked_file_options(self, query: str, options: list[str]) -> list[str]:
        ranked_options = [
            (rank, option)
            for option in options
            if (rank := self.get_file_option_rank(query, option)) is not None
        ]
        ranked_options.sort(key=lambda item: item[0])
        return [option for _, option in ranked_options]

    def get_visible_file_options(self, options: list[str]) -> list[str]:
        return options[:self.MAX_OPTIONS]

    def get_cached_file_options(self, query: str, require_min_results: bool = True) -> Optional[list[str]]:
        cached = self.option_cache.get(query)
        if cached:
            cached_at, options = cached
            if self.is_file_option_cache_fresh(cached_at):
                self.option_cache.move_to_end(query)
                return self.get_visible_file_options(options)
            self.option_cache.pop(query)

        for cached_query, (cached_at, options) in reversed(list(self.option_cache.items())):
            is_refinement = query.startswith(cached_query)
            is_backtrack = cached_query.startswith(query)
            if (is_refinement or is_backtrack) and self.is_file_option_cache_fresh(cached_at):
                self.option_cache.move_to_end(cached_query)
                filtered_options = self.get_ranked_file_options(query, options)
                if len(filtered_options) >= self.FILE_OPTION_CACHE_MIN_RESULTS or (
                    filtered_options and not require_min_results
                ):
                    if is_refinement:
                        self.cache_file_options(query, filtered_options)
                    return self.get_visible_file_options(filtered_options)
        return None

    def cache_file_options(self, query: str, options: list[str]):
        self.option_cache[query] = (monotonic(), options[:self.FILE_OPTION_CACHE_RESULT_SIZE])
        self.option_cache.move_to_end(query)
        while len(self.option_cache) > self.FILE_OPTION_CACHE_SIZE:
            self.option_cache.popitem(last=False)

    def fetch_file_options(self, query: str, use_path_scheme: bool = True) -> Optional[list[str]]:
        fd_args = ['fd', '-apu', '-tf', '-E', '/nix', '-E', '/sys', '.', '/']
        fzf_args = ['fzf', '-f', query]
        if use_path_scheme:
            fzf_args.insert(1, '--scheme=path')
        head_args = ['head', '-n', str(self.FILE_OPTION_CACHE_RESULT_SIZE)]
        command = ' | '.join(map(shlex.join, [fd_args, fzf_args, head_args]))
        try:
            with self.option_fetch_lock:
                _, command_stdout, command_stderr = self.remote_client.ssh.exec_command(command, timeout=self.FILE_OPTION_FETCH_TIMEOUT)
                try:
                    options = command_stdout.read().decode().splitlines()
                    stderr = command_stderr.read().decode(errors='replace').casefold()
                finally:
                    command_stdout.channel.close()
        except (OSError, TimeoutError, socket.timeout):
            return None
        if use_path_scheme and not options and ('unknown option' in stderr or 'invalid option' in stderr):
            return self.fetch_file_options(query, use_path_scheme=False)
        return options

    def finish_file_options(self, query: str, options: Optional[list[str]]):
        self.option_fetches.discard(query)
        if options is None:
            return

        self.cache_file_options(query, options)
        input_box = self.query_one(Input)
        current_query = self.get_file_query_at_cursor(input_box.value, input_box.cursor_position)
        if current_query != query:
            return

        self.show_option_list(self.get_visible_file_options(options))

    def load_file_options(self, query: str):
        options = self.fetch_file_options(query)
        self.call_from_thread(self.finish_file_options, query, options)

    def request_file_options(self, query: str):
        if query in self.option_fetches:
            return

        self.option_fetches.add(query)
        self.run_worker(
            lambda: self.load_file_options(query),
            name='sensai-options',
            group='sensai-options',
            exclusive=False,
            exit_on_error=False,
            thread=True,
        )

    def cancel_option_update_timer(self):
        if self.option_update_timer:
            self.option_update_timer.stop()
            self.option_update_timer = None

    def on_input_changed(self, event: Input.Changed):
        self.cancel_option_update_timer()
        self.option_update_timer = self.set_timer(self.OPTION_UPDATE_DELAY, self.update_option_list)

    def select_option(self):
        input_box = self.query_one(Input)
        input_box.focus()

        if input_box.value.startswith('/') or input_box.value.startswith('!'):
            input_box.value = self.user_message
            input_box.action_end()
        else:
            if ' ' in input_box.value[:input_box.cursor_position]:
                left_index = input_box.value[:input_box.cursor_position].rindex(' ') + 1
            else:
                left_index = 0

            if ' ' in input_box.value[left_index:]:
                right_index = left_index + input_box.value[left_index:].index(' ')
            else:
                right_index = len(input_box.value)

            input_box.value = input_box.value[:left_index] + f'@{self.user_message}' + input_box.value[right_index:]
            input_box.cursor_position = left_index + len(f'@{self.user_message}')

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

def run_simple(base_url: str, session_cookie: str, timeout: Optional[float]):
    with Session() as session:
        session.cookies.set_cookie(create_cookie('session', session_cookie))
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

                    try:
                        event = sio.receive(timeout=timeout)
                    except TimeoutError:
                        if timeout is None:
                            fail('SensAI did not respond.')
                        else:
                            fail(f'SensAI timed out after {timeout:g} seconds.')
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

def init_sensai(simple: bool = False, timeout: float = DEFAULT_SENSAI_TIMEOUT):
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

    sensai_timeout = None if timeout <= 0 else timeout
    if simple:
        run_simple(base_url, cookie_jar['session'], sensai_timeout)
    else:
        app = SensaiApp(base_url, cookie_jar['session'], sensai_timeout)
        app.run()
