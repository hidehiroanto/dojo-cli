"""Handles challenge initialization and flag submission."""

import os
import re
import string
from pathlib import Path

from bs4 import BeautifulSoup
from itsdangerous import URLSafeSerializer
from rich.markdown import Markdown

from .client import get_remote_client
from .http import request
from .log import error, fail, info, success, warn
from .terminal import apply_style
from .utils import can_render_image, download_image, fix_markdown_links, get_belt_hex, require_item, show_table

SECTIONS = ['welcome', 'topic', 'public', 'course', 'private', 'hidden', 'example']


def sort_dojos(dojos: list[dict]) -> list[dict]:
    """Sort dojos into website category order while preserving API order."""
    indexed_dojos = enumerate(dojos)
    return [
        dojo
        for _, dojo in sorted(
            indexed_dojos,
            key=lambda item: (
                SECTIONS.index(item[1].get('type')) if item[1].get('type') in SECTIONS else len(SECTIONS),
                item[0],
            ),
        )
    ]


def validate_dojo_path(parts: list[str], offset: int = 0) -> bool:
    """Return whether path components contain valid dojo identifiers."""
    patterns = (r'[-~\w]+', r'[-\w]+', r'[-\w]+')
    return all(re.fullmatch(pattern, part) for pattern, part in zip(patterns[offset:], parts))


def parse_challenge_path(challenge_id: str, challenge_data: dict | None = None) -> tuple:
    absolute = challenge_id.startswith('/')
    parts = challenge_id.strip('/').split('/')
    offset = 3 - len(parts)
    if not 1 <= len(parts) <= 3 or not validate_dojo_path(parts, offset):
        return ()
    if absolute:
        return tuple(parts) if len(parts) == 3 else ()
    if len(parts) == 3:
        return tuple(parts)
    if not challenge_data:
        challenge_data = request('/docker').json()
    if not challenge_data.get('success'):
        return ()
    if len(parts) == 2:
        return challenge_data.get('dojo'), parts[0], parts[1]
    return challenge_data.get('dojo'), challenge_data.get('module'), parts[0]


def parse_catalog_path(path: str) -> tuple[str | None, str | None, str | None]:
    """Parse an absolute dojo catalog path."""
    if not path.startswith('/'):
        raise ValueError('List and tree paths must start with /.')
    parts = path.strip('/').split('/') if path != '/' else []
    if len(parts) > 3 or not validate_dojo_path(parts):
        raise ValueError('Invalid dojo catalog path.')
    padded = parts + [None] * (3 - len(parts))
    return padded[0], padded[1], padded[2]


def resolve_catalog_path(
    path: str | None, dojo_id: str | None, module_id: str | None, challenge_id: str | None
) -> tuple[str | None, str | None, str | None]:
    """Resolve a positional catalog path or component options."""
    if path is None:
        return dojo_id, module_id, challenge_id
    if any(value is not None for value in (dojo_id, module_id, challenge_id)):
        error('Path cannot be combined with --dojo, --module, or --challenge.')
    try:
        return parse_catalog_path(path)
    except ValueError as exc:
        error(str(exc))


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

    challenge_data = request('/docker').json()

    if challenge_id:
        if not dojo_id or not module_id:
            challenge_path = parse_challenge_path(challenge_id, challenge_data)
            if len(challenge_path) == 3 and all(isinstance(s, str) for s in challenge_path):
                dojo_id, module_id, challenge_id = challenge_path
            else:
                error('Invalid challenge ID.')

        challenge_num_id = get_challenge_num_id(dojo_id, module_id, challenge_id)
        if challenge_num_id == -1:
            error('Challenge does not exist.')
    else:
        if challenge_data['success']:
            dojo_id, module_id, challenge_id = (challenge_data['dojo'], challenge_data['module'], challenge_data['challenge'])
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
        flag_size = get_remote_client().getsize(str(flag_path))
        if flag_size == -1:
            error('Flag file does not exist.')
        return flag_size

    else:
        error('No active challenge session; start a challenge!')

    return -1


def show_list(
    path: str | None = None,
    dojo_id: str | None = None,
    module_id: str | None = None,
    challenge_id: str | None = None,
    auth: bool = False,
    official: bool = False,
    simple: bool = False,
    ids: bool = False,
):
    dojo_id, module_id, challenge_id = resolve_catalog_path(path, dojo_id, module_id, challenge_id)
    if not dojo_id:
        dojos = request('/dojos', auth=auth).json().get('dojos')
        sorted_dojos = sort_dojos(dojos)
        if official:
            sorted_dojos = [dojo for dojo in sorted_dojos if dojo['official']]
        if ids:
            print(*(dojo['id'] for dojo in sorted_dojos), sep='\n')
            return

        render_image = not simple and can_render_image()
        table_data = []
        table_title = 'List of Dojos'
        table_keys = ['id', 'award', 'name', 'description', 'modules', 'challenges']

        for dojo in sorted_dojos:
            if not dojo['award']:
                award = None
            elif 'belt' in dojo['award']:
                if render_image:
                    award = download_image(f'/belt/{dojo["award"]["belt"]}.svg')
                else:
                    belt_hex = get_belt_hex(dojo['award']['belt'])
                    award = f'[b {belt_hex}]{dojo["award"]["belt"].title()} Belt[/]'
            elif 'emoji' in dojo['award']:
                award = dojo['award']['emoji']

            table_data.append(
                {
                    'id': f'[b cyan]{dojo["id"]}[/]',
                    'award': award,
                    'name': f'[b green]{dojo["name"]}[/]',
                    'description': Markdown(fix_markdown_links(dojo['description'])) if dojo['description'] else None,
                    'modules': dojo['modules_count'],
                    'challenges': dojo['challenges_count'],
                }
            )

    elif not module_id:
        modules = request(f'/dojos/{dojo_id}/modules', auth=auth).json().get('modules')
        if ids:
            print(*(module['id'] for module in modules), sep='\n')
            return
        table_data = []
        table_title = f'List of Modules in {dojo_id}'
        table_keys = ['id', 'name', 'description']

        for module in modules:
            table_data.append(
                {
                    'id': f'[b cyan]{module["id"]}[/]',
                    'name': f'[b green]{module["name"]}[/]',
                    'description': Markdown(fix_markdown_links(module['description'])) if module['description'] else None,
                }
            )

    elif not challenge_id:
        modules = request(f'/dojos/{dojo_id}/modules', auth=auth).json().get('modules')
        module = require_item(modules, module_id, 'Module')
        if ids:
            print(*(challenge['id'] for challenge in module['challenges']), sep='\n')
            return
        table_data = []
        table_title = module.get('name') or module['id']
        table_keys = ['type', 'id', 'name', 'content']

        for item in module['unified_items']:
            item_type = item['item_type']
            resource_type = item.get('type')
            if item_type == 'resource' and resource_type == 'header':
                if table_data:
                    show_table(table_data, table_title, table_keys, column_overflow='fold', show_lines=True)
                table_data = []
                table_title = item.get('content') or item.get('name') or 'Resources'
                continue

            content = item.get('content') or item.get('description') or ''
            if item_type == 'resource' and resource_type == 'lecture':
                links = []
                if item.get('video'):
                    youtube_url = f'https://www.youtube.com/watch?v={item["video"]}'
                    if item.get('playlist'):
                        youtube_url += f'&list={item["playlist"]}'
                    links.append(f'Video: [{youtube_url}]({youtube_url})')
                if item.get('slides'):
                    slides_url = f'https://docs.google.com/presentation/d/{item["slides"]}/embed'
                    links.append(f'Slides: [{slides_url}]({slides_url})')
                content = '\n\n'.join(links)

            label = item_type.title()
            if item_type == 'resource':
                label = resource_type.title()
            table_data.append(
                {
                    'type': label,
                    'id': f'[b cyan]{item["id"]}[/]' if item.get('id') else None,
                    'name': f'[b green]{item["name"]}[/]' if item.get('name') else None,
                    'content': Markdown(fix_markdown_links(content)) if content else None,
                }
            )
        show_table(table_data, table_title, table_keys, column_overflow='fold', show_lines=True)
        return
    else:
        modules = request(f'/dojos/{dojo_id}/modules', auth=auth).json().get('modules')
        challenges = require_item(modules, module_id, 'Module').get('challenges', [])
        table_data = require_item(challenges, challenge_id, 'Challenge')
        if ids:
            print(table_data['id'])
            return
        table_title = f'Challenge Info for {dojo_id}/{module_id}/{challenge_id}'
        table_keys = ['id', 'name', 'description']

        table_data['id'] = f'[b cyan]{table_data["id"]}[/]'
        table_data['name'] = f'[b green]{table_data["name"]}[/]'
        table_data['description'] = (
            Markdown(fix_markdown_links(table_data['description'])) if table_data['description'] else None
        )

    show_table(table_data, table_title, table_keys, show_lines=True)


def init_challenge(
    path: str | None = None,
    dojo_id: str | None = None,
    module_id: str | None = None,
    challenge_id: str | None = None,
    standard: bool = False,
    privileged: bool = False,
):
    challenge_data = request('/docker').json()

    if path is not None:
        if any(value is not None for value in (dojo_id, module_id, challenge_id)):
            error('Path cannot be combined with --dojo, --module, or --challenge.')
        challenge_path = parse_challenge_path(path, challenge_data)
        if len(challenge_path) != 3:
            error('Could not parse challenge path.')
        dojo_id, module_id, challenge_id = challenge_path
    elif not challenge_id:
        if challenge_data['success']:
            dojo_id, module_id, challenge_id = (challenge_data['dojo'], challenge_data['module'], challenge_data['challenge'])
        else:
            error('No active challenge session; please specify a challenge ID!')
    elif not dojo_id or not module_id:
        challenge_path = parse_challenge_path(challenge_id, challenge_data)
        if len(challenge_path) == 3 and all(isinstance(s, str) for s in challenge_path):
            dojo_id, module_id, challenge_id = challenge_path
        else:
            error('Could not parse challenge ID.')

    if get_challenge_num_id(dojo_id, module_id, challenge_id) == -1:
        error('Challenge does not exist.')

    if privileged:
        practice = True
    elif standard:
        practice = False
    else:
        practice = challenge_data.get('practice', False)

    challenge_data = {'dojo': dojo_id, 'module': module_id, 'challenge': challenge_id, 'practice': practice}
    docker_response = request('/docker', csrf=True, json=challenge_data).json()
    if docker_response.get('success'):
        success('Challenge started successfully!')
    elif docker_response.get('error'):
        error(docker_response['error'])
    else:
        error('Failed to start challenge.')


def init_next(standard: bool = False, privileged: bool = False):
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_next = active_module.json().get('c_next')
    if c_next:
        init_challenge(
            dojo_id=c_next['dojo_reference_id'],
            module_id=c_next['module_id'],
            challenge_id=c_next['challenge_reference_id'],
            standard=standard,
            privileged=privileged,
        )
    else:
        warn('This is the last challenge in the module.')


def init_previous(standard: bool = False, privileged: bool = False):
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    active_module = request('/active-module', False)
    if active_module.is_redirect:
        error('Please login first.')

    c_previous = active_module.json().get('c_previous')
    if c_previous:
        init_challenge(
            dojo_id=c_previous['dojo_reference_id'],
            module_id=c_previous['module_id'],
            challenge_id=c_previous['challenge_reference_id'],
            standard=standard,
            privileged=privileged,
        )
    else:
        warn('This is the first challenge in the module.')


def restart_challenge(standard: bool = False, privileged: bool = False):
    if not request('/docker').json().get('success'):
        error('No active challenge session; start a challenge!')

    init_challenge(standard=standard, privileged=privileged)


def stop_challenge():
    docker_response = request('/docker', csrf=True, method='DELETE', json={}).json()
    if docker_response.get('success'):
        success(docker_response.get('message', 'Challenge stopped successfully!'))
    else:
        error(docker_response.get('error', 'Challenge stopped unsuccessfully.'))


def show_status():
    docker_response = request('/docker').json()
    if docker_response.get('success'):
        docker_response.pop('success')
        show_table(docker_response, 'Challenge Status')
    else:
        fail(docker_response.get('error'))


def show_hint(dojo_id: str | None = None, module_id: str | None = None, challenge_id: str | None = None):
    (dojo_id, module_id, challenge_id), (account_id, challenge_num_id) = get_challenge_info(dojo_id, module_id, challenge_id)

    fake_flag = serialize_flag(account_id, challenge_num_id)
    flag_prefix = 'pwn.college{'
    flag_suffix = fake_flag[fake_flag.index('.') :] + '}'
    info(f'The flag starts with: [b cyan]{flag_prefix}[/]')
    info(f'The flag ends with: [b cyan]{flag_suffix}[/]')
    flag_chars = ''.join(sorted(string.digits + string.ascii_letters + '-_'))
    info(f'The middle of the flag can only be these characters: [b cyan]{flag_chars}[/]')

    challenge_data = request('/docker').json()
    if list(map(challenge_data.get, ['dojo', 'module', 'challenge', 'practice'])) == [dojo_id, module_id, challenge_id, False]:
        flag_length = get_flag_size() - 1
        flag_path = Path('/flag')
        warn(f'The following information assumes that {apply_style(flag_path)} has not been tampered with:')
        info(f'Excluding the final newline, the flag is {flag_length} characters long.')
        middle_count = flag_length - len(flag_prefix) - len(flag_suffix)
        info(f'You only need to figure out the middle {middle_count} characters of the flag.')

    else:
        flag_length = len(f'pwn.college{{{fake_flag}}}')
        warn('You are not running the correct challenge in standard mode, so the real flag size cannot be measured.')
        info(f'Excluding the final newline, the flag is about {flag_length} characters long.')
        info(f'You would only need to figure out the middle {fake_flag.index(".")} characters of the flag.')


def submit_flag(
    flag: str | None = None, dojo_id: str | None = None, module_id: str | None = None, challenge_id: str | None = None
):
    (dojo_id, module_id, challenge_id), (account_id, challenge_num_id) = get_challenge_info(dojo_id, module_id, challenge_id)

    while not flag:
        flag = input('Enter the flag: ').strip()

    if flag in ['practice', 'pwn.college{practice}']:
        warn('This is the practice flag!')
        info('Restart the challenge in standard mode to get the real flag.')
        info('(You can do this with [b]dojo restart [green]-s[/][/].)')
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

        challenge_data = request('/docker').json()
        if list(map(challenge_data.get, ['dojo', 'module', 'challenge', 'practice'])) == [
            dojo_id,
            module_id,
            challenge_id,
            False,
        ]:
            flag_length = get_flag_size() - 1
        else:
            flag_length = len(f'pwn.college{{{serialize_flag(account_id, challenge_num_id)}}}')

        full_flag_mismatch = (
            re.fullmatch(r'pwn\.college\{[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.?\}', flag) and len(flag) != flag_length
        )
        partial_flag_mismatch = (
            re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.?', flag) and len(f'pwn.college{{{flag}}}') != flag_length
        )
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

    # TODO: Tell the user whether the flag is correct even if the challenge is
    # already solved. CTFd fixed this in CTFd/CTFd#2651, but pwn.college has
    # not merged it.
    #
    # response = request(
    #     '/api/v1/challenges/attempt',
    #     False,
    #     csrf='DOJO_AUTH_TOKEN' not in os.environ,
    #     json={'challenge_id': challenge_id, 'submission': flag}
    # )
    # rprint(response.json().get('data').get('message'))

    solve_response = request(
        f'/dojos/{dojo_id}/{module_id}/{challenge_id}/solve',
        csrf='DOJO_AUTH_TOKEN' not in os.environ,
        json={'submission': flag},
    )

    if solve_response.ok:
        if solve_response.json().get('status') == 'solved':
            success('The flag is correct! You have successfully solved the challenge!')
        elif solve_response.json().get('status') == 'already_solved':
            warn('You have already solved this challenge!')
        else:
            info(str(solve_response.json()))
    elif solve_response.status_code == 400:
        if solve_response.json().get('status') == 'incorrect':
            fail('The flag is incorrect.')
        else:
            error(str(solve_response.json()))
    elif solve_response.status_code == 404:
        if solve_response.json().get('error') == 'Challenge not found':
            error('The challenge does not exist.')
        else:
            error(str(solve_response.json()))
    else:
        error(f'Failed to submit the flag (code: {solve_response.status_code}).')
