"""
Handles video playback for Twitch and YouTube.
"""

from pathlib import Path
from shutil import which
import subprocess
from typing import Optional

from .config import load_user_config
from .constants import UNAME_SYSTEM
from .http import request
from .install import homebrew_install, wax_install, zerobrew_install
from .log import error

def play_twitch(channel: str):
    user_config = load_user_config()
    package_manager = user_config['package_manager'][UNAME_SYSTEM]

    twitch_url = f'https://twitch.tv/{channel}'

    if UNAME_SYSTEM == 'Darwin':
        if not Path(which('iina') or '/Applications/IINA.app/Contents/MacOS/iina-cli').is_file():
            if package_manager == 'homebrew':
                homebrew_install(casks=['iina'])
            elif package_manager == 'wax':
                wax_install(casks=['iina'])
            elif package_manager == 'zerobrew':
                zerobrew_install(casks=['iina'])

        iina_cli = Path(which('iina') or '/Applications/IINA.app/Contents/MacOS/iina-cli')
        subprocess.run([iina_cli, twitch_url])

    elif UNAME_SYSTEM == 'Linux':
        if not Path(which('mpv') or '/usr/bin/mpv').is_file():
            if package_manager == 'homebrew':
                homebrew_install(['mpv'])
            elif package_manager == 'wax':
                wax_install(['mpv'])
            elif package_manager == 'zerobrew':
                zerobrew_install(['mpv'])

        from mpv import MPV
        player = MPV()
        player.play(twitch_url)
        player.wait_for_shutdown()

    else:
        error(f'Unsupported platform: {UNAME_SYSTEM}')

def play_youtube(youtube_id: str, playlist: Optional[str] = None):
    user_config = load_user_config()
    package_manager = user_config['package_manager'][UNAME_SYSTEM]

    youtube_url = f'https://www.youtube.com/watch?v={youtube_id}'
    if playlist:
        youtube_url += f'&list={playlist}'

    if UNAME_SYSTEM == 'Darwin':
        if not Path(which('iina') or '/Applications/IINA.app/Contents/MacOS/iina-cli').is_file():
            if package_manager == 'homebrew':
                homebrew_install(casks=['iina'])
            elif package_manager == 'wax':
                wax_install(casks=['iina'])
            elif package_manager == 'zerobrew':
                zerobrew_install(casks=['iina'])

        iina_cli = Path(which('iina') or '/Applications/IINA.app/Contents/MacOS/iina-cli')
        iina_args = [iina_cli, youtube_url, '--mpv-ytdl=yes']
        if playlist:
            iina_args.append('--mpv-ytdl-raw-options="yes-playlist="')
        subprocess.run(iina_args)

    elif UNAME_SYSTEM == 'Linux':
        if not Path(which('mpv') or '/usr/bin/mpv').is_file():
            if package_manager == 'homebrew':
                homebrew_install(['mpv'])
            elif package_manager == 'wax':
                wax_install(['mpv'])
            elif package_manager == 'zerobrew':
                zerobrew_install(['mpv'])

        from mpv import MPV
        player = MPV(ytdl=True, ytdl_raw_options='yes-playlist=')
        player.play(youtube_url)
        player.wait_for_shutdown()

    else:
        error(f'Unsupported platform: {UNAME_SYSTEM}')

def init_twitch():
    play_twitch('pwncollege')

def init_youtube(dojo_id: str, module_id: str, resource_id: str):
    modules = request(f'/dojos/{dojo_id}/modules').json().get('modules')
    module = next(filter(lambda module: module['id'] == module_id, modules))
    resource = next(filter(lambda resource: resource['id'] == resource_id, module['resources']))
    if resource['type'] == 'lecture':
        play_youtube(resource.get('video'), resource.get('playlist'))
    else:
        error('Not a lecture.')
