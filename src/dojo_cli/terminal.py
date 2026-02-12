import datetime
from pathlib import Path
import re

from .config import load_user_config

def apply_style(obj):
    object_styles = load_user_config()['object_styles']

    if isinstance(obj, str):
        if re.match(r'^[\w\-\.]+@([\w\-]+\.)+[\w\-]{2,4}$', obj):
            style = f'{object_styles['email']} link=mailto:{obj}'
        elif obj.startswith('http://') or obj.startswith('https://'):
            style = f'{object_styles['url']} link={obj}'
        else:
            return obj

    elif isinstance(obj, Path):
        if obj == Path() or obj.parent == Path():
            style = object_styles['filename']
        elif obj == Path('/'):
            style = object_styles['path']
        elif obj.parent == Path('/'):
            return f'[{object_styles['path']}]/[/][{object_styles['filename']}]{obj.name}[/]'
        else:
            return f'[{object_styles['path']}]{obj.parent}/[/][{object_styles['filename']}]{obj.name}[/]'

    elif isinstance(obj, datetime.datetime):
        return f'[{object_styles['date']}]{obj.date()}[/] [{object_styles['time']}]{obj.time()}[/]'

    else:
        type_name = type(obj).__name__
        if str(obj) in object_styles:
            style = object_styles[str(obj)]
        elif type_name in object_styles:
            style = object_styles[type_name]
        else:
            return obj

    return f'[{style}]{obj}[/]'
