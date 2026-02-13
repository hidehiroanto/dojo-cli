"""
Handles challenge initialization and flag submission.
"""

from bs4 import BeautifulSoup
from itsdangerous import URLSafeSerializer
import os
import re
from pathlib import Path
import string

from .http import request
from .log import error, fail, info, success, warn
from .remote import run_cmd, ssh_getsize
from .terminal import apply_style

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
            if input('(y/N) > ').strip()[0].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

        if payload[1] != challenge_num_id:
            warn('This flag is from another challenge! Are you sure you want to submit?')
            if input('(y/N) > ').strip()[0].lower() != 'y':
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
            if input('(y/N) > ').strip()[0].lower() != 'y':
                warn('Aborting flag submission attempt!')
                return

    else:
        warn('Could not deserialize flag. Are you sure you want to submit?')
        if input('(y/N) > ').strip()[0].lower() != 'y':
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
