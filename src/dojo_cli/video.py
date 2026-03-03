"""
Handles video playback for Twitch and YouTube.
"""

from pathlib import Path
from shutil import which
import subprocess
from typing import Optional
import yt_dlp

from .config import load_user_config
from .constants import UNAME_SYSTEM
from .http import request
from .install import homebrew_install, wax_install, zerobrew_install
from .log import error
from .utils import can_render_image, download_image, show_table

def play_twitch(channel: str):
    user_config = load_user_config()
    package_manager = user_config['package_manager'][UNAME_SYSTEM]

    twitch_url = f'https://www.twitch.tv/{channel}'

    if 'isLiveBroadcast' not in request(twitch_url, False, False).text:
        error(f'No live stream found for {channel}')
        return

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

    youtube_url = video_id if video_id.startswith('https://') else f'https://www.youtube.com/watch?v={video_id}'
    if playlist_id:
        youtube_url += f'&list={playlist_id}' if '?' in youtube_url else f'?list={playlist_id}'

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
    video_id: Optional[str] = None,
    playlist_id: Optional[str] = None,
    dojo_id: Optional[str] = None,
    module_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    page: Optional[int] = None,
    simple: bool = False
):
    if video_id is not None:
        play_youtube(video_id, playlist_id)

    elif dojo_id is not None and module_id is not None and resource_id is not None:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        module = next(filter(lambda module: module['id'] == module_id, modules))
        resource = next(filter(lambda resource: resource['id'] == resource_id, module['resources']))
        if resource['type'] == 'lecture':
            play_youtube(resource.get('video'), resource.get('playlist'))
        else:
            error(f'The resource with the ID {resource_id} is not a lecture, it is of type "{resource['type']}".')

    else:
        with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True, 'skip_download': True}) as ydl:
            if playlist_id is not None:
                feed = ydl.extract_info(f'https://www.youtube.com/playlist?list={playlist_id}')['entries']
            else:
                feed = ydl.extract_info('https://www.youtube.com/pwncollege')['entries'][0]['entries']

        if page is not None:
            feed = feed[page * 20:][:20]

        render_image = not simple and can_render_image()
        for row in feed:
            row['id'] = f'[b cyan]{row['id']}[/]'
            row['title'] = f'[b green]{row['title']}[/]'
            if render_image:
                row['thumbnail'] = download_image(row['thumbnails'][0]['url'], 3)

        table_keys = ['id', 'thumbnail', 'title', 'url'] if render_image else ['id', 'title', 'url']
        show_table(feed, 'YouTube Feed', table_keys)
