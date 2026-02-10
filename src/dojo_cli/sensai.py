"""
Handles SensAI.
"""

from pathlib import Path
from requests import Session
from rich import print as rprint
from rich.markdown import Markdown
from socketio import SimpleClient

from .config import load_user_config
from .log import error, info
from .utils import check_challenge_session, load_cookie

def init_sensai():
    if not check_challenge_session():
        error('No active challenge session; start a challenge!')

    user_config = load_user_config()
    base_url = user_config['base_url']
    cookie_path = Path(user_config['cookie_path'])
    if not cookie_path.is_file():
        error('Login first')

    cookie_jar = load_cookie(cookie_path) or {}
    if not cookie_jar:
        error('Invalid cookie')

    headers = {'Cookie': f'session={cookie_jar['session']};'}

    with Session() as session:
        session.get(base_url + '/sensai/', headers=headers)
        headers['Cookie'] += f'sensai_session={session.cookies.get('sensai_session')};'

    with SimpleClient() as client:
        client.connect(base_url, headers, transports=['websocket'], socketio_path='sensai/socket.io')
        while True:
            info('Type message and press enter (press [bold cyan]^C[/] to exit):')
            content = {'message': input(), 'terminal': '...', 'file': '...'}
            client.emit('new_interaction', {'type': 'learner', 'content': content})
            assistant_message = client.receive()[1]['content']['message']
            info('SensAI response:')
            rprint(Markdown(assistant_message))
