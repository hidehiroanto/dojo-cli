"""
Handles video playback for Twitch and YouTube.
"""

from datetime import datetime
from pathlib import Path
from shutil import which
import subprocess
from typing import Optional
import xmltodict

from .config import load_user_config
from .constants import UNAME_SYSTEM
from .http import request
from .install import homebrew_install, wax_install, zerobrew_install
from .log import error
from .utils import show_table

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

def play_youtube(video_id: str, playlist_id: Optional[str] = None):
    user_config = load_user_config()
    package_manager = user_config['package_manager'][UNAME_SYSTEM]

    youtube_url = f'https://www.youtube.com/watch?v={video_id}'
    if playlist_id:
        youtube_url += f'&list={playlist_id}'

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
        if playlist_id:
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

def init_youtube(
    dojo_id: Optional[str] = None,
    module_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    playlist_id: Optional[str] = None,
    video_id: Optional[str] = None
):
    if video_id is not None:
        play_youtube(video_id, playlist_id)

    elif dojo_id is not None and module_id is not None and resource_id is not None:
        modules = request(f'/dojos/{dojo_id}/modules').json().get('modules')
        module = next(filter(lambda module: module['id'] == module_id, modules))
        resource = next(filter(lambda resource: resource['id'] == resource_id, module['resources']))
        if resource['type'] == 'lecture':
            play_youtube(resource.get('video'), resource.get('playlist'))
        else:
            error(f'The resource with the ID {resource_id} is not a lecture, it is of type "{resource['type']}".')

    else:
        feed_url = 'https://www.youtube.com/feeds/videos.xml?'
        feed_url += f'playlist_id={playlist_id}' if playlist_id is not None else 'channel_id=UCBaWwFw7KmCN8YlfX4ERYKg'
        feed = xmltodict.parse(request(feed_url, auth=False).text)['feed']['entry']

        for row in feed:
            row['id'] = f'[b cyan]{row['yt:videoId']}[/]'
            row['title'] = f'[b green]{row['title']}[/]'
            row['link'] = row['link']['@href']
            row['published'] = datetime.fromisoformat(row['published'])
            row['updated'] = datetime.fromisoformat(row['updated'])

        show_table(feed, 'YouTube Feed', ['id', 'title', 'link', 'published', 'updated'])
