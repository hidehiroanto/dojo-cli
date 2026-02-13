"""
Handles challenge initialization and flag submission.
"""

from bs4 import BeautifulSoup
from itsdangerous import URLSafeSerializer
import os
import re
from rich.markdown import Markdown
from pathlib import Path
import string

from .http import request
from .log import error, fail, info, success, warn
from .remote import run_cmd, ssh_getsize
from .terminal import apply_style
from .utils import can_render_image, download_image, get_belt_hex, show_table

def parse_challenge_path(challenge_id: str, challenge_data: dict = {}) -> tuple:
    if re.fullmatch(r'[\-\w]+', challenge_id):
        if not challenge_data:
            challenge_data = request('/docker').json()
        if challenge_data.get('success'):
            return challenge_data.get('dojo'), challenge_data.get('module'), challenge_id
        return tuple()

    result = re.findall(r'/?([\-\~\w]+)/([\-\w]+)/([\-\w]+)', challenge_id)
    return result[0] if result else tuple()

def get_challenge_num_id(dojo_id: str | None, module_id: str | None, challenge_id: str | None) -> int:
    if dojo_id and module_id and challenge_id:
        response = request(f'/{dojo_id}/{module_id}', False, False)
        soup = BeautifulSoup(response.text, 'html.parser')
        challenges = soup.find_all('div', class_='challenge-init')
        for challenge_div in challenges:
            input_challenge = challenge_div.find('input', id='challenge')
            if input_challenge and input_challenge['value'] == challenge_id:
                input_challenge_id = challenge_div.find('input', id='challenge-id')
                if input_challenge_id:
                    return int(str(input_challenge_id['value']))
    return -1

def get_challenge_info(dojo_id: str | None = None, module_id: str | None = None, challenge_id: str | None = None):
    account_id = request('/users/me').json().get('id')
    if account_id is None:
        error('Please login first or run this in the dojo.')

    chal_data = request('/docker').json()

    if challenge_id:
        if not dojo_id or not module_id:
            challenge_path = parse_challenge_path(challenge_id, chal_data)
            if len(challenge_path) == 3 and all(isinstance(s, str) for s in challenge_path):
                dojo_id, module_id, challenge_id = challenge_path
            else:
                error('Invalid challenge ID.')

        challenge_num_id = get_challenge_num_id(dojo_id, module_id, challenge_id)
        if challenge_num_id == -1:
            error('Challenge does not exist.')
    else:
        if chal_data['success']:
            dojo_id, module_id, challenge_id = chal_data['dojo'], chal_data['module'], chal_data['challenge']
        else:
            error('No active challenge session; please start a challenge or specify a challenge name!')

        active_module = request('/active-module', False)
        if active_module.is_redirect:
            challenge_num_id = get_challenge_num_id(dojo_id, module_id, challenge_id)
        else:
            challenge_num_id = active_module.json().get('c_current', {}).get('challenge_id', -1)

    return (dojo_id, module_id, challenge_id), (account_id, challenge_num_id)

def serialize_flag(account_id: int, challenge_id: int) -> str:
    return URLSafeSerializer('').dumps([account_id, challenge_id])[::-1]

def deserialize_flag(flag: str) -> list[int] | None:
    return URLSafeSerializer('').loads_unsafe(re.sub('.+?{(.+)}', r'\1', flag)[::-1])[1]

def get_flag_size() -> int:
    flag_path = Path('/flag')

    if 'DOJO_AUTH_TOKEN' in os.environ:
        if flag_path.is_file():
            return flag_path.stat().st_size
        else:
            error('Flag file does not exist.')

    elif request('/docker').json().get('success'):
        flag_size = ssh_getsize(flag_path)
        if flag_size == -1:
            error('Flag file does not exist.')
        return flag_size

    else:
        error('No active challenge session; start a challenge!')

    return -1

def show_list(dojo_id: str | None = None, module_id: str | None = None, challenge_id: str | None = None, official: bool = False, simple: bool = False):
    if not dojo_id:
        dojos = request('/dojos', auth=False).json().get('dojos')
        if official:
            dojos = filter(lambda dojo: dojo['official'], dojos)
        # TODO: sort dojos
        render_image = not simple and can_render_image()
        table_data = []
        table_title = 'List of Dojos'
        table_keys = ['id', 'award', 'name', 'description', 'modules', 'challenges']

        for dojo_id in dojos:
            if not dojo_id['award']:
                award = None
            elif 'belt' in dojo_id['award']:
                if render_image:
                    award = download_image(f'/belt/{dojo_id['award']['belt']}.svg', 'belt')
                else:
                    belt_hex = get_belt_hex(dojo_id['award']['belt'])
                    award = f'[bold {belt_hex}]{dojo_id['award']['belt'].title()} Belt[/]'
            elif 'emoji' in dojo_id['award']:
                award = dojo_id['award']['emoji']

            table_data.append({
                'id': f'[bold cyan]{dojo_id['id']}[/]',
                'award': award,
                'name': f'[bold green]{dojo_id['name']}[/]',
                'description': Markdown(dojo_id['description']) if dojo_id['description'] else None,
                'modules': dojo_id['modules_count'],
                'challenges': dojo_id['challenges_count']
            })
    elif not module_id:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        table_data = []
        table_title = f'List of Modules in {dojo_id}'
        table_keys = ['id', 'name', 'description']

        for module_id in modules:
            table_data.append({
                'id': f'[bold cyan]{module_id['id']}[/]',
                'name': f'[bold green]{module_id['name']}[/]',
                'description': Markdown(module_id['description']) if module_id['description'] else None
            })
    elif not challenge_id:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        module = next(filter(lambda module: module['id'] == module_id, modules))
        resources = list(filter(lambda resource: resource['type'] != 'header', module['resources']))

        if resources:
            resource_title = f'List of Resources in {dojo_id}/{module_id}'
            resource_keys = ['name', 'type', 'content']

            for resource in resources:
                resource['id'] = f'[bold cyan]{resource['id']}[/]'
                resource['name'] = f'[bold green]{resource['name']}[/]'
                if resource['type'] == 'lecture':
                    resource['content'] = ''
                    if 'video' in resource:
                        youtube_url = f'https://www.youtube.com/watch?v={resource['video']}'
                        if 'playlist' in resource:
                            youtube_url += f'&list={resource['playlist']}'
                        resource['content'] += f'Video: [blue link={youtube_url}]{youtube_url}[/]\n'
                    if 'slides' in resource:
                        slides_url = f'https://docs.google.com/presentation/d/{resource['slides']}/embed'
                        resource['content'] += f'Slides: [blue link={slides_url}]{slides_url}[/]\n'
                    resource['content'] = resource['content'].strip()
                if resource['type'] == 'markdown':
                    resource['content'] = Markdown(resource['content'])
                resource['type'] = resource['type'].title()
            show_table(resources, resource_title, resource_keys, show_lines=True)

        table_data = []
        table_title = f'List of Challenges in {dojo_id}/{module_id}'
        table_keys = ['id', 'name', 'description']

        for challenge_id in module['challenges']:
            table_data.append({
                'id': f'[bold cyan]{challenge_id['id']}[/]',
                'name': f'[bold green]{challenge_id['name']}[/]',
                'description': Markdown(challenge_id['description']) if challenge_id['description'] else None
            })
    else:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        challenges = next(filter(lambda module: module['id'] == module_id, modules)).get('challenges')
        table_data = next(filter(lambda challenge: challenge['id'] == challenge_id, challenges))
        table_title = f'Challenge Info for {dojo_id}/{module_id}/{challenge_id}'
        table_keys = ['id', 'name', 'description']

        table_data['id'] = f'[bold cyan]{table_data['id']}[/]'
        table_data['name'] = f'[bold green]{table_data['name']}[/]'
        table_data['description'] = Markdown(table_data['description']) if table_data['description'] else None

    show_table(table_data, table_title, table_keys, show_lines=True)

def init_challenge(dojo_id: str | None = None, module_id: str | None = None, challenge_id: str | None = None, normal: bool = False, privileged: bool = False):
    chal_data = request('/docker').json()

    if not challenge_id:
        if chal_data['success']:
            dojo_id, module_id, challenge_id = chal_data['dojo'], chal_data['module'], chal_data['challenge']
        else:
            error('No active challenge session; please specify a challenge ID!')
    elif not dojo_id or not module_id:
        challenge_path = parse_challenge_path(challenge_id, chal_data)
        if len(challenge_path) == 3 and all(isinstance(s, str) for s in challenge_path):
            dojo_id, module_id, challenge_id = challenge_path
        else:
            error('Could not parse challenge ID.')

    if get_challenge_num_id(dojo_id, module_id, challenge_id) == -1:
        error('Challenge does not exist.')

    if privileged:
        practice = True
    elif normal:
        practice = False
    else:
        practice = chal_data.get('practice', False)

    request_json = {'dojo': dojo_id, 'module': module_id, 'challenge': challenge_id, 'practice': practice}
    response = request('/docker', csrf=True, json=request_json).json()
    if response.get('success'):
        success('Challenge started successfully!')
    elif response.get('error'):
        error(response['error'])
    else:
        error('Failed to start challenge.')

def init_next(normal: bool = False, privileged: bool = False):
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_next = active_module.json().get('c_next')
    if c_next:
        init_challenge(c_next['dojo_reference_id'], c_next['module_id'], c_next['challenge_reference_id'], normal, privileged)
    else:
        warn('This is the last challenge in the module.')

def init_previous(normal: bool = False, privileged: bool = False):
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_previous = active_module.json().get('c_previous')
    if c_previous:
        init_challenge(c_previous['dojo_reference_id'], c_previous['module_id'], c_previous['challenge_reference_id'], normal, privileged)
    else:
        warn('This is the first challenge in the module.')

def restart_challenge(normal: bool = False, privileged: bool = False):
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    init_challenge(normal=normal, privileged=privileged)

def show_status():
    response = request('/docker').json()
    if response.get('success'):
        response.pop('success')
        show_table(response, 'Challenge Status')
    else:
        fail(response.get('error'))

def stop_challenge():
    response = request('/docker').json()
    if response.get('success'):
        if response.get('practice'):
            run_cmd('sudo kill 1', True)
            if not request('/docker').json().get('success'):
                success('Challenge stopped successfully!')
        else:
            error('Challenge is in normal mode, cannot stop container without root privileges.')
    else:
        error('No active challenge session; start a challenge!')

def show_hint(dojo_id: str | None = None, module_id: str | None = None, challenge_id: str | None = None):
    (dojo_id, module_id, challenge_id), (account_id, challenge_num_id) = get_challenge_info(dojo_id, module_id, challenge_id)

    fake_flag = serialize_flag(account_id, challenge_num_id)
    flag_prefix = 'pwn.college{'
    flag_suffix = fake_flag[fake_flag.index('.'):] + '}'
    info(f'The flag starts with: [bold cyan]{flag_prefix}[/]')
    info(f'The flag ends with: [bold cyan]{flag_suffix}[/]')
    flag_chars = ''.join(sorted(string.digits + string.ascii_letters + '-_'))
    info(f'The middle of the flag can only be these characters: [bold cyan]{flag_chars}[/]')

    chal_data = request('/docker').json()
    if list(map(chal_data.get, ['dojo', 'module', 'challenge', 'practice'])) == [dojo_id, module_id, challenge_id, False]:
        flag_length = get_flag_size() - 1
        flag_path = Path('/flag')
        warn(f'The following information assumes that {apply_style(flag_path)} has not been tampered with:')
        info(f'Excluding the final newline, the flag is {flag_length} characters long.')
        middle_count = flag_length - len(flag_prefix) - len(flag_suffix)
        info(f'You only need to figure out the middle {middle_count} characters of the flag.')

    else:
        flag_length = len(f'pwn.college{{{fake_flag}}}')
        warn('You are not running the correct challenge in normal mode, so the real flag size cannot be measured.')
        info(f'Excluding the final newline, the flag is about {flag_length} characters long.')
        info(f'You would only need to figure out the middle {fake_flag.index('.')} characters of the flag.')

def submit_flag(flag: str | None = None, dojo_id: str | None = None, module_id: str | None = None, challenge_id: str | None = None):
    (dojo_id, module_id, challenge_id), (account_id, challenge_num_id) = get_challenge_info(dojo_id, module_id, challenge_id)

    while not flag:
        flag = input('Enter the flag: ').strip()

    if flag in ['practice', 'pwn.college{practice}']:
        warn('This is the practice flag!')
        info('Restart the challenge in normal mode to get the real flag.')
        info('(You can do this with [bold]dojo restart [green]-n[/][/].)')
        return

    payload = deserialize_flag(flag)

    if isinstance(payload, list) and len(payload) == 2 and all(isinstance(i, int) for i in payload):
        if payload[0] != account_id:
            warn('This flag is from another account! Are you sure you want to submit?')
            if input('(y/N) > ').strip()[:1].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

        if payload[1] != challenge_num_id:
            warn('This flag is from another challenge! Are you sure you want to submit?')
            if input('(y/N) > ').strip()[:1].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

        chal_data = request('/docker').json()
        if list(map(chal_data.get, ['dojo', 'module', 'challenge', 'practice'])) == [dojo_id, module_id, challenge_id, False]:
            flag_length = get_flag_size() - 1
        else:
            flag_length = len(f'pwn.college{{{serialize_flag(account_id, challenge_num_id)}}}')

        full_flag_mismatch = re.fullmatch(r'pwn.college{[\-\.\w]+}', flag) and len(flag) != flag_length
        partial_flag_mismatch = re.fullmatch(r'[\-\.\w]+', flag) and len(f'pwn.college{{{flag}}}') != flag_length
        if full_flag_mismatch or partial_flag_mismatch:
            warn(f'This flag is the wrong size! The real flag length is {flag_length}. Are you sure you want to submit?')
            if input('(y/N) > ').strip()[:1].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

    else:
        warn('Could not deserialize flag. Are you sure you want to submit?')
        if input('(y/N) > ').strip()[:1].lower() != 'y':
            warn('Aborting flag submission attempt!')
            return

    info(f'Submitting the flag: {flag}')

    # TODO: Tell user whether the flag is correct or not even if the challenge is already solved
    # I fixed this already in CTFd (https://github.com/CTFd/CTFd/pull/2651) but pwn.college never merged it
    #
    # response = request(
    #     '/api/v1/challenges/attempt',
    #     False,
    #     csrf='DOJO_AUTH_TOKEN' not in os.environ,
    #     json={'challenge_id': challenge_id, 'submission': flag}
    # )
    # rprint(response.json().get('data').get('message'))

    response = request(
        f'/dojos/{dojo_id}/{module_id}/{challenge_id}/solve',
        csrf='DOJO_AUTH_TOKEN' not in os.environ,
        json={'submission': flag}
    )

    result = response.json()

    if response.ok:
        if result.get('status') == 'solved':
            success('The flag is correct! You have successfully solved the challenge!')
        elif result.get('status') == 'already_solved':
            warn('You have already solved this challenge!')
        else:
            info(str(result))
    elif response.status_code == 400:
        if result.get('status') == 'incorrect':
            fail('The flag is incorrect.')
        else:
            error(str(result))
    elif response.status_code == 404:
        if result.get('error') == 'Challenge not found':
            error('The challenge does not exist.')
        else:
            error(str(result))
    else:
        error(f'Failed to submit the flag (code: {response.status_code}).')
