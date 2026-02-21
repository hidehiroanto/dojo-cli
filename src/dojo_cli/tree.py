"""
Handles the tree view TUI.
"""

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Label, Markdown, MarkdownViewer, Tree
from typing import Optional

from .http import request
from .challenge import DOJO_IDS, init_challenge
from .utils import fix_markdown_links

ROOT_LABEL = 'up/down: move, space: toggle, enter: select, ctrl+p: palette, ctrl+q: quit'
ROOT_DESCRIPTION = """
| Key(s) | Description |
| :- | :- |
| enter | Select the current item. |
| space | Toggle the expand/collapsed state of the current item. |
| up | Move the cursor up. |
| down | Move the cursor down. |
"""

class DescriptionViewer(MarkdownViewer):
    async def _on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        message.prevent_default()
        message.stop()

class StartChallengeModal(ModalScreen):
    CSS = """
    StartChallengeModal {
        align: center middle;
    }

    StartChallengeModal > Container {
        width: auto;
        height: auto;
        padding: 1 2;
        background: $panel;
    }

    StartChallengeModal > Container > Horizontal {
        align: center middle;
        width: 100%;
        height: auto;
    }

    StartChallengeModal > Container > Horizontal > Button {
        margin: 1 2;
    }
    """

    def __init__(self, dojo_id: str, module_id: str, challenge_id: str, practice: bool):
        super().__init__()
        self.dojo_id = dojo_id
        self.module_id = module_id
        self.challenge_id = challenge_id
        self.practice = practice

    def compose(self) -> ComposeResult:
        with Container():
            challenge_path = f'{self.dojo_id}/{self.module_id}/{self.challenge_id}'
            challenge_mode = 'privileged' if self.practice else 'unprivileged'
            yield Label(f'Start challenge [bold]{challenge_path}[/] in {challenge_mode} mode?')
            with Horizontal():
                yield Button.error('Cancel')
                yield Button.success('Start Challenge')

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.variant == 'success':
            if self.practice:
                init_challenge(self.dojo_id, self.module_id, self.challenge_id, privileged=True)
            else:
                init_challenge(self.dojo_id, self.module_id, self.challenge_id, normal=True)
            self.app.exit()
        elif event.button.variant == 'error':
            self.dismiss()

class TreeApp(App):
    def __init__(
        self,
        dojo_id: Optional[str] = None,
        module_id: Optional[str] = None,
        challenge_id: Optional[str] = None,
        auth: bool = False,
        official: bool = False
    ):
        super().__init__()
        dojos = request('/dojos', auth=auth).json().get('dojos')
        sorted_dojos = sorted(filter(lambda dojo: dojo['id'] in DOJO_IDS, dojos), key=lambda dojo: DOJO_IDS.index(dojo['id']))
        sorted_dojos += sorted(filter(lambda dojo: dojo['id'] not in DOJO_IDS, dojos), key=lambda dojo: dojo['id'])

        if not dojo_id:
            self.data = {}
            if official:
                sorted_dojos = filter(lambda dojo: dojo['official'], sorted_dojos)
            for dojo in sorted_dojos:
                self.data[dojo['id']] = {'data': dojo, 'modules': {}}
                modules = request(f'/dojos/{dojo['id']}/modules', auth=auth).json().get('modules')
                for module in modules:
                    self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
                    for item in module['unified_items']:
                        self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

        elif not module_id:
            dojo = next(filter(lambda dojo: dojo['id'] == dojo_id, sorted_dojos))
            self.data = {dojo_id: {'data': dojo, 'modules': {}}}
            modules = request(f'/dojos/{dojo_id}/modules', auth=auth).json().get('modules')
            for module in modules:
                self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
                for item in module['unified_items']:
                    self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

        elif not challenge_id:
            dojo = next(filter(lambda dojo: dojo['id'] == dojo_id, sorted_dojos))
            self.data = {dojo_id: {'data': dojo, 'modules': {}}}
            modules = request(f'/dojos/{dojo_id}/modules', auth=auth).json().get('modules')
            module = next(filter(lambda module: module['id'] == module_id, modules))
            self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
            for item in module['unified_items']:
                self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

        else:
            dojo = next(filter(lambda dojo: dojo['id'] == dojo_id, sorted_dojos))
            self.data = {dojo_id: {'data': dojo, 'modules': {}}}
            modules = request(f'/dojos/{dojo_id}/modules', auth=auth).json().get('modules')
            module = next(filter(lambda module: module['id'] == module_id, modules))
            self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
            for item in module['unified_items']:
                if item['item_type'] == 'resource' or item['item_type'] == 'challenge' and item['id'] == challenge_id:
                    self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

    def compose(self) -> ComposeResult:
        tree = Tree(ROOT_LABEL, {'description': ROOT_DESCRIPTION})
        tree.root.expand()
        for dojo_id, dojo in self.data.items():
            dojo_node = tree.root.add(Text(f'Dojo: {dojo['data']['name']}', 'markdown.h1'), dojo['data'])
            for module_id, module in dojo['modules'].items():
                module_node = dojo_node.add(Text(f'Module: {module['data']['name']}', 'markdown.h2'), module['data'])
                for item_id, item in module['unified_items'].items():
                    if item['data']['item_type'] == 'resource':
                        if item['data']['type'] == 'header':
                            module_node.add_leaf(Text(item['data']['content'], 'markdown.h3'))
                        elif item['data']['type'] == 'lecture':
                            item['data']['description'] = ''
                            if item['data'].get('video'):
                                youtube_url = f'https://www.youtube.com/watch?v={item['data']['video']}'
                                if item['data'].get('playlist'):
                                    youtube_url += f'&list={item['data']['playlist']}'
                                item['data']['description'] += f'Video: [{youtube_url}]({youtube_url})\n\n'
                            if item['data'].get('slides'):
                                slides_url = f'https://docs.google.com/presentation/d/{item['data']['slides']}/embed'
                                item['data']['description'] += f'Slides: [{slides_url}]({slides_url})\n\n'
                            module_node.add_leaf(f'Lecture: {item['data']['name']}', item['data'])
                        elif item['data']['type'] == 'markdown':
                            item['data']['description'] = item['data']['content']
                            module_node.add_leaf(f'Resource: {item['data']['name']}', item['data'])
                    elif item['data']['item_type'] == 'challenge':
                        item['data'].update({'dojo': dojo_id, 'module': module_id, 'challenge': item_id})
                        challenge_node = module_node.add(f'Challenge: {item['data']['name']}', item['data'])
                        challenge_node.add_leaf('Start Challenge', item['data'])
                        # TODO: disable privileged mode if not available
                        challenge_node.add_leaf('Start Challenge in Privileged Mode', item['data'])

        with Horizontal():
            yield tree
            yield DescriptionViewer(show_table_of_contents=False)
        yield Footer()

    def on_mount(self):
        self.call_after_refresh(lambda: self.query_one(DescriptionViewer).query_one(Markdown).update(ROOT_DESCRIPTION))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted):
        description = ''
        if event.node.data and event.node.data.get('description'):
            description = fix_markdown_links(event.node.data['description'])
        self.query_one(DescriptionViewer).query_one(Markdown).update(description)

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        node_label = str(event.node.label)

        if node_label == 'Start Challenge':
            node_data = event.node.data
            assert node_data
            self.push_screen(StartChallengeModal(node_data['dojo'], node_data['module'], node_data['challenge'], False))

        elif node_label == 'Start Challenge in Privileged Mode':
            node_data = event.node.data
            assert node_data
            self.push_screen(StartChallengeModal(node_data['dojo'], node_data['module'], node_data['challenge'], True))

def init_tree(
    dojo_id: Optional[str] = None,
    module_id: Optional[str] = None,
    challenge_id: Optional[str] = None,
    auth: bool = False,
    official: bool = False
):
    app = TreeApp(dojo_id, module_id, challenge_id, auth, official)
    app.run()
