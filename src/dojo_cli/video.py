"""Handles video playback for Twitch and YouTube."""

import subprocess
from pathlib import Path

import yt_dlp

from .constants import UNAME_SYSTEM, XDG_BIN_HOME
from .http import request
from .install import configured_package_manager, package_manager_install, require_executable
from .log import error
from .utils import can_render_image, download_image, paginate, require_item, show_table


def require_iina() -> Path:
    """Resolve IINA, installing it after confirmation if needed."""
    package_manager = configured_package_manager()
    return require_executable(
        'iina',
        [XDG_BIN_HOME / 'iina', '/Applications/IINA.app/Contents/MacOS/iina-cli'],
        display_name='IINA',
        installer=lambda: package_manager_install(casks=['iina'], packages=['iina']),
        method=package_manager,
    )


def require_mpv() -> Path:
    """Resolve mpv, installing it after confirmation if needed."""
    package_manager = configured_package_manager()
    return require_executable(
        'mpv',
        [XDG_BIN_HOME / 'mpv', '/usr/local/bin/mpv', '/usr/bin/mpv'],
        installer=lambda: package_manager_install(formulae=['mpv'], packages=['mpv']),
        method=package_manager,
    )


def play_twitch(channel: str):
    twitch_url = f'https://www.twitch.tv/{channel}'

    if 'isLiveBroadcast' not in request(twitch_url, False, False).text:
        error(f'No live stream found for {channel}')
        return

    if UNAME_SYSTEM == 'Darwin':
        iina_cli = require_iina()
        completed = subprocess.run([str(iina_cli), twitch_url], check=False)
        if completed.returncode:
            raise SystemExit(completed.returncode)

    elif UNAME_SYSTEM == 'Linux':
        require_mpv()

        from mpv import MPV

        player = MPV()
        player.play(twitch_url)
        player.wait_for_shutdown()

    else:
        error(f'Unsupported platform: {UNAME_SYSTEM}')


def play_youtube(video_id: str, playlist_id: str | None = None):
    youtube_url = video_id if video_id.startswith('https://') else f'https://www.youtube.com/watch?v={video_id}'
    if playlist_id:
        youtube_url += f'&list={playlist_id}' if '?' in youtube_url else f'?list={playlist_id}'

    if UNAME_SYSTEM == 'Darwin':
        iina_cli = require_iina()
        iina_args = [iina_cli, youtube_url, '--mpv-ytdl=yes']
        if playlist_id:
            iina_args.append('--mpv-ytdl-raw-options="yes-playlist="')
        completed = subprocess.run([str(arg) for arg in iina_args], check=False)
        if completed.returncode:
            raise SystemExit(completed.returncode)

    elif UNAME_SYSTEM == 'Linux':
        require_mpv()

        from mpv import MPV

        player = MPV(ytdl=True, ytdl_raw_options='yes-playlist=')
        player.play(youtube_url)
        player.wait_for_shutdown()

    else:
        error(f'Unsupported platform: {UNAME_SYSTEM}')


def init_twitch():
    play_twitch('pwncollege')


def init_youtube(
    video_id: str | None = None,
    playlist_id: str | None = None,
    dojo_id: str | None = None,
    module_id: str | None = None,
    resource_id: str | None = None,
    page: int | None = None,
    simple: bool = False,
):
    if video_id is not None:
        play_youtube(video_id, playlist_id)

    elif dojo_id is not None and module_id is not None and resource_id is not None:
        modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
        module = require_item(modules, module_id, 'Module')
        resource = require_item(module['resources'], resource_id, 'Resource')
        if resource['type'] == 'lecture':
            video = resource.get('video')
            if not video:
                error(f'The lecture with the ID {resource_id} does not have a video.')
            play_youtube(video, resource.get('playlist'))
        else:
            error(f'The resource with the ID {resource_id} is not a lecture, it is of type "{resource["type"]}".')

    else:
        with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True, 'skip_download': True}) as ydl:
            if playlist_id is not None:
                feed = ydl.extract_info(f'https://www.youtube.com/playlist?list={playlist_id}')['entries']
            else:
                feed = ydl.extract_info('https://www.youtube.com/pwncollege')['entries'][0]['entries']

        feed = paginate(feed, page)

        render_image = not simple and can_render_image()
        for row in feed:
            row['id'] = f'[b cyan]{row["id"]}[/]'
            row['title'] = f'[b green]{row["title"]}[/]'
            duration = int(row['duration'])
            row['duration'] = f'{duration // 3600:02}:{(duration % 3600) // 60:02}:{duration % 60:02}'
            if render_image:
                row['thumbnail'] = download_image(row['thumbnails'][0]['url'], 3)

        table_keys = ['id', 'thumbnail', 'title', 'url', 'duration'] if render_image else ['id', 'title', 'url', 'duration']
        show_table(feed, 'YouTube Feed', table_keys)
