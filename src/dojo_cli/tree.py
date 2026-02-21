"""
Handles the tree view TUI.
"""

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Markdown, MarkdownViewer, Tree
from typing import Optional

from .http import request
from .challenge import init_challenge

ROOT_LABEL = 'up/down: move, space/click arrow: toggle, enter/click node: select, ctrl+q: quit'
ROOT_DESCRIPTION = """
| Key(s) | Description |
| :- | :- |
| enter | Select the current item. |
| space | Toggle the expand/collapsed state of the current item. |
| up | Move the cursor up. |
| down | Move the cursor down. |
"""

class TreeApp(App):
    def __init__(
        self,
        dojo_id: Optional[str] = None,
        module_id: Optional[str] = None,
        challenge_id: Optional[str] = None,
        official: bool = False
    ):
        super().__init__()
        dojos = request('/dojos', auth=False).json().get('dojos')

        if not dojo_id:
            self.data = {}
            if official:
                dojos = filter(lambda dojo: dojo['official'], dojos)
            for dojo in dojos:
                self.data[dojo['id']] = {'data': dojo, 'modules': {}}
                modules = request(f'/dojos/{dojo['id']}/modules', auth=False).json().get('modules')
                for module in modules:
                    self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
                    for item in module['unified_items']:
                        if item['item_type'] == 'resource' and item['type'] != 'header' or item['item_type'] == 'challenge':
                            self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

        elif not module_id:
            dojo = next(filter(lambda dojo: dojo['id'] == dojo_id, dojos))
            self.data = {dojo_id: {'data': dojo, 'modules': {}}}
            modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
            for module in modules:
                self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
                for item in module['unified_items']:
                    if item['item_type'] == 'resource' and item['type'] != 'header' or item['item_type'] == 'challenge':
                        self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

        elif not challenge_id:
            dojo = next(filter(lambda dojo: dojo['id'] == dojo_id, dojos))
            self.data = {dojo_id: {'data': dojo, 'modules': {}}}
            modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
            module = next(filter(lambda module: module['id'] == module_id, modules))
            self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
            for item in module['unified_items']:
                if item['item_type'] == 'resource' and item['type'] != 'header' or item['item_type'] == 'challenge':
                    self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

        else:
            dojo = next(filter(lambda dojo: dojo['id'] == dojo_id, dojos))
            self.data = {dojo_id: {'data': dojo, 'modules': {}}}
            modules = request(f'/dojos/{dojo_id}/modules', auth=False).json().get('modules')
            module = next(filter(lambda module: module['id'] == module_id, modules))
            self.data[dojo['id']]['modules'][module['id']] = {'data': module, 'unified_items': {}}
            for item in module['unified_items']:
                if item['item_type'] == 'resource' and item['type'] != 'header' or item['item_type'] == 'challenge' and item['id'] == challenge_id:
                    self.data[dojo['id']]['modules'][module['id']]['unified_items'][item['id']] = {'data': item}

    def compose(self) -> ComposeResult:
        tree = Tree(ROOT_LABEL, {'description': ROOT_DESCRIPTION})
        tree.root.expand()
        for dojo_id, dojo in self.data.items():
            dojo_node = tree.root.add(f'Dojo: {dojo['data']['name']}', dojo['data'])
            for module_id, module in dojo['modules'].items():
                module_node = dojo_node.add(f'Module: {module['data']['name']}', module['data'])
                for item_id, item in module['unified_items'].items():
                    if item['data']['item_type'] == 'resource':
                        if item['data']['type'] == 'lecture':
                            item['data']['description'] = ''
                            if item['data'].get('video'):
                                youtube_url = f'https://www.youtube.com/watch?v={item['data']['video']}'
                                if item['data'].get('playlist'):
                                    youtube_url += f'&list={item['data']['playlist']}'
                                item['data']['description'] += f'Video: [{youtube_url}]({youtube_url})\n\n'
                            if item['data'].get('slides'):
                                slides_url = f'https://docs.google.com/presentation/d/{item['data']['slides']}/embed'
                                item['data']['description'] += f'Slides: [{slides_url}]({slides_url})\n\n'
                        elif item['data']['type'] == 'markdown':
                            item['data']['description'] = item['data']['content']
                        module_node.add_leaf(f'Resource: {item['data']['name']}', item['data'])
                    elif item['data']['item_type'] == 'challenge':
                        challenge_node = module_node.add(f'Challenge: {item['data']['name']}', item['data'])
                        challenge_node.add_leaf('Start Challenge', item['data'])
                        # TODO: disable practice mode if not available
                        challenge_node.add_leaf('Start Challenge in Privileged Mode', item['data'])

        with Horizontal():
            yield tree
            yield MarkdownViewer()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted):
        if event.node.data:
            self.query_one(Markdown).update(event.node.data['description'])

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        node_label = str(event.node.label)

        if node_label == 'Start Challenge':
            challenge_node = event.node.parent
            assert challenge_node and challenge_node.data
            challenge_id = challenge_node.data['id']

            module_node = challenge_node.parent
            assert module_node and module_node.data
            module_id = module_node.data['id']

            dojo_node = module_node.parent
            assert dojo_node and dojo_node.data
            dojo_id = dojo_node.data['id']

            init_challenge(dojo_id, module_id, challenge_id, normal=True)
            self.exit()

        elif node_label == 'Start Challenge in Privileged Mode':
            challenge_node = event.node.parent
            assert challenge_node and challenge_node.data
            challenge_id = challenge_node.data['id']

            module_node = challenge_node.parent
            assert module_node and module_node.data
            module_id = module_node.data['id']

            dojo_node = module_node.parent
            assert dojo_node and dojo_node.data
            dojo_id = dojo_node.data['id']

            init_challenge(dojo_id, module_id, challenge_id, privileged=True)
            self.exit()

def init_tree(
    dojo_id: Optional[str] = None,
    module_id: Optional[str] = None,
    challenge_id: Optional[str] = None,
    official: bool = False
):
    app = TreeApp(dojo_id, module_id, challenge_id, official)
    app.run()
