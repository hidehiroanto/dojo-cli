"""Handles the tree view TUI."""

from typing import ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Label,
    Markdown,
    MarkdownViewer,
    Static,
    Tree,
)

from .challenge import resolve_catalog_path, sort_dojos
from .http import authentication_available, request
from .log import error
from .utils import fix_markdown_links, require_item

ROOT_LABEL = 'Challenge Browser'
ROOT_DESCRIPTION = """
| Key(s) | Description |
| :- | :- |
| enter | Select the current item. |
| space | Toggle the expanded state. |
| j/down, k/up | Move the cursor. |
| h/left, l/right | Collapse or expand. |
| gg, G | Move to the top or bottom. |
"""


def display_name(item: dict, fallback: str) -> str:
    """Return the best available display name for a catalog item."""
    return item.get('name') or item.get('id') or f'Unnamed {fallback}'


def render_details(data: dict | None, can_start: bool = True) -> str:
    """Render details for a highlighted tree node."""
    if not data:
        return ROOT_DESCRIPTION

    kind = data.get('item_type')
    description = data.get('description') or data.get('content') or ''
    if kind == 'resource' and data.get('type') == 'header':
        details = [f'## {description}']
    elif kind == 'challenge':
        required = data.get('required')
        required_text = 'yes' if required else 'no' if required is not None else '?'
        start_text = (
            'Press `enter` to choose Standard or Privileged mode.'
            if can_start
            else 'Log in to start this challenge.'
        )
        details = [
            f'# {display_name(data, "challenge")}',
            '',
            description,
            '',
            f'- Challenge ID: `{data.get("id", "?")}`',
            f'- Required: `{required_text}`',
            '',
            start_text,
        ]
        if data.get('allow_privileged') is False:
            details.extend(['', 'Privileged mode is unavailable for this challenge.'])
    elif kind == 'resource':
        details = [
            f'# {display_name(data, "resource")}',
            '',
            description,
            '',
            f'- Resource ID: `{data.get("id", "?")}`',
            f'- Type: `{data.get("type", "?")}`',
        ]
    elif 'modules_count' in data:
        details = [
            f'# {display_name(data, "dojo")}',
            '',
            description,
            '',
            f'- Dojo ID: `{data.get("id", "?")}`',
            f'- Modules: `{data.get("modules_count", 0)}`',
            f'- Challenges: `{data.get("challenges_count", 0)}`',
        ]
    elif 'challenges' in data:
        details = [
            f'# {display_name(data, "module")}',
            '',
            description,
            '',
            f'- Module ID: `{data.get("id", "?")}`',
            f'- Challenges: `{len(data.get("challenges", []))}`',
            f'- Resources: `{len(data.get("resources", []))}`',
        ]
    else:
        return ROOT_DESCRIPTION
    return fix_markdown_links('\n'.join(details))


class DescriptionViewer(MarkdownViewer):
    async def _on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        message.prevent_default()
        message.stop()


class VimTree(Tree):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding('j', 'vim_down', 'Down', show=False),
        Binding('k', 'vim_up', 'Up', show=False),
        Binding('h', 'vim_left', 'Collapse', show=False),
        Binding('l', 'vim_right', 'Expand', show=False),
        Binding('g', 'vim_top', 'Top', show=False),
        Binding('G', 'vim_bottom', 'Bottom', show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._count = ''
        self._pending_g = False

    def on_key(self, event):
        if (
            event.character
            and event.character.isdigit()
            and (event.character != '0' or self._count)
        ):
            self._count += event.character
            self._pending_g = False
            event.stop()
            event.prevent_default()
            return
        if event.key not in ('j', 'k', 'h', 'l', 'g', 'G'):
            self._count = ''
        if event.key != 'g':
            self._pending_g = False

    def take_count(self) -> int:
        count = int(self._count) if self._count else 1
        self._count = ''
        return count

    def move_cursor_by(self, delta: int) -> None:
        self.cursor_line = max(self.cursor_line, 0) + delta
        self.scroll_to_line(self.cursor_line, animate=False)

    def action_vim_down(self) -> None:
        self.move_cursor_by(self.take_count())

    def action_vim_up(self) -> None:
        self.move_cursor_by(-self.take_count())

    def action_vim_left(self) -> None:
        self.take_count()
        node = self.cursor_node
        if node and node.allow_expand and node.is_expanded:
            node.collapse()
        else:
            self.action_cursor_parent()

    def action_vim_right(self) -> None:
        self.take_count()
        node = self.cursor_node
        if not node:
            return
        if node.allow_expand and not node.is_expanded:
            node.expand()
        elif node.children:
            self.move_cursor_by(1)

    def action_vim_top(self) -> None:
        if not self._pending_g:
            self._pending_g = True
            return
        self._pending_g = False
        self.take_count()
        self.cursor_line = 0
        self.scroll_to_line(self.cursor_line, animate=False)

    def action_vim_bottom(self) -> None:
        self.take_count()
        self.cursor_line = self.last_line
        self.scroll_to_line(self.cursor_line, animate=False)


class StartChallengeModal(ModalScreen):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding('s', 'start_standard', 'Standard'),
        Binding('p', 'start_privileged', 'Privileged'),
        Binding('escape', 'cancel', 'Cancel'),
    ]
    CSS = """
    StartChallengeModal {
        align: center middle;
    }

    StartChallengeModal > Container {
        width: 64;
        max-width: 100%;
        height: auto;
        padding: 1 2;
        background: $panel;
    }

    #mode-actions, #cancel-actions {
        align: center middle;
        width: 100%;
        height: auto;
    }

    #mode-actions Button {
        margin: 1;
    }

    #cancel-actions Button {
        margin: 0 1;
    }

    #start-error {
        color: $error;
        height: auto;
    }

    #start-note {
        color: $warning;
        height: auto;
    }
    """

    def __init__(self, dojo: dict, module: dict, challenge: dict):
        super().__init__()
        self.dojo = dojo
        self.module = module
        self.challenge = challenge
        self.allow_privileged = challenge.get('allow_privileged')
        self.last_mode_id = 'standard'

    def compose(self) -> ComposeResult:
        with Container():
            summary = Text('Start Challenge\n', style='bold')
            for label, item, fallback in (
                ('Dojo', self.dojo, 'dojo'),
                ('Module', self.module, 'module'),
                ('Challenge', self.challenge, 'challenge'),
            ):
                summary.append(f'{label}: ')
                summary.append(display_name(item, fallback), style='bold')
                summary.append(f' ({item["id"]})\n', style='dim')
            yield Label(summary)
            yield Label('', id='start-error')
            note = (
                'Privileged mode is unavailable for this challenge.'
                if self.allow_privileged is False
                else ''
            )
            yield Label(note, id='start-note')
            with Horizontal(id='mode-actions'):
                yield Button('Standard', id='standard', variant='success')
                yield Button(
                    'Privileged',
                    id='privileged',
                    variant='warning',
                    disabled=self.allow_privileged is False,
                )
            with Horizontal(id='cancel-actions'):
                yield Button('Cancel', id='cancel')

    def on_key(self, event) -> None:
        focused_id = self.focused.id if self.focused else None
        target_id = None
        privileged_available = self.allow_privileged is not False
        if (
            focused_id == 'standard'
            and event.key in ('left', 'right')
            and privileged_available
        ):
            target_id = 'privileged'
        elif focused_id == 'privileged' and event.key in ('left', 'right'):
            target_id = 'standard'
        elif focused_id in ('standard', 'privileged') and event.key == 'down':
            self.last_mode_id = focused_id
            target_id = 'cancel'
        elif focused_id == 'cancel' and event.key == 'up':
            target_id = (
                self.last_mode_id
                if self.last_mode_id != 'privileged' or privileged_available
                else 'standard'
            )
        elif focused_id == 'cancel' and event.key == 'left':
            target_id = 'standard'
        elif focused_id == 'cancel' and event.key == 'right':
            target_id = 'privileged' if privileged_available else 'standard'
        if target_id:
            self.query_one(f'#{target_id}', Button).focus()
            event.prevent_default()
            event.stop()

    def start_challenge(self, practice: bool) -> None:
        payload = {
            'dojo': self.dojo['id'],
            'module': self.module['id'],
            'challenge': self.challenge['id'],
            'practice': practice,
        }
        response = request('/docker', csrf=True, json=payload).json()
        if response.get('success'):
            self.app.exit(True)
            return
        message = response.get('error') or 'Failed to start challenge.'
        if practice and 'does not support practice mode' in message.lower():
            self.allow_privileged = False
            self.challenge['allow_privileged'] = False
            self.last_mode_id = 'standard'
            self.query_one('#privileged', Button).disabled = True
            self.query_one('#standard', Button).focus()
            self.query_one('#start-note', Label).update(
                'Privileged mode is unavailable for this challenge.'
            )
        self.query_one('#start-error', Label).update(message)

    def action_start_standard(self) -> None:
        self.start_challenge(False)

    def action_start_privileged(self) -> None:
        if self.allow_privileged is not False:
            self.start_challenge(True)

    def action_cancel(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'standard':
            self.action_start_standard()
        elif event.button.id == 'privileged':
            self.action_start_privileged()
        else:
            self.action_cancel()


class TreeApp(App):
    CSS = """
    #details {
        height: 1fr;
    }

    #status {
        height: 1;
        padding: 0 1;
    }
    """
    BINDINGS: ClassVar = [
        Binding('q', 'quit', 'Quit'),
        Binding('r', 'reload', 'Reload', priority=True),
    ]

    def __init__(
        self,
        dojo_id: str | None = None,
        module_id: str | None = None,
        challenge_id: str | None = None,
        auth: bool = False,
        official: bool = False,
        can_start: bool = True,
    ):
        super().__init__()
        self.dojo_id = dojo_id
        self.module_id = module_id
        self.challenge_id = challenge_id
        self.auth = auth
        self.official = official
        self.can_start = can_start
        self.data = {}
        self.loaded_modules = set()
        self.node_index = {}
        self.load_catalog()

    def load_catalog(self) -> None:
        dojos = request('/dojos', auth=self.auth).json().get('dojos')
        sorted_dojos = sort_dojos(dojos)

        if not self.dojo_id:
            if self.official:
                sorted_dojos = [dojo for dojo in sorted_dojos if dojo['official']]
            selected_dojos = sorted_dojos
        else:
            selected_dojos = [require_item(sorted_dojos, self.dojo_id, 'Dojo')]

        self.data = {
            dojo['id']: {'data': dojo, 'modules': {}} for dojo in selected_dojos
        }
        self.loaded_modules = set()
        if self.dojo_id:
            self.load_initial_modules(
                self.data[self.dojo_id]['data'], self.module_id, self.challenge_id
            )

    def load_initial_modules(
        self,
        dojo: dict,
        module_id: str | None = None,
        challenge_id: str | None = None,
    ) -> None:
        modules = (
            request(f'/dojos/{dojo["id"]}/modules', auth=self.auth)
            .json()
            .get('modules')
        )
        selected_modules = (
            [require_item(modules, module_id, 'Module')] if module_id else modules
        )
        for module in selected_modules:
            self.store_module(dojo['id'], module, challenge_id)
        self.loaded_modules.add(dojo['id'])

    def store_module(
        self, dojo_id: str, module: dict, challenge_id: str | None = None
    ) -> None:
        module_data = dict(module)
        module_data['_dojo_id'] = dojo_id
        items = module['unified_items']
        if challenge_id:
            items = [
                item
                for item in items
                if item['item_type'] == 'resource'
                or item['item_type'] == 'challenge'
                and item['id'] == challenge_id
            ]
        unified_items = {}
        for item in items:
            item_data = dict(item)
            item_data['_dojo_id'] = dojo_id
            item_data['_module_id'] = module['id']
            unified_items[item['id']] = {'data': item_data}
        self.data[dojo_id]['modules'][module['id']] = {
            'data': module_data,
            'unified_items': unified_items,
        }

    def data_key(self, data: dict | None) -> tuple | None:
        if not data:
            return None
        if data.get('item_type') in ('challenge', 'resource'):
            return (
                data['item_type'],
                data['_dojo_id'],
                data['_module_id'],
                data['id'],
            )
        if '_dojo_id' in data and 'challenges' in data:
            return 'module', data['_dojo_id'], data['id']
        if 'modules_count' in data:
            return 'dojo', data['id']
        return None

    def add_module_node(self, dojo_node, module: dict) -> None:
        module_node = dojo_node.add(
            Text(f'Module: {display_name(module["data"], "module")}', 'markdown.h2'),
            module['data'],
        )
        self.node_index[self.data_key(module['data'])] = module_node
        for item in module['unified_items'].values():
            data = item['data']
            item_node = None
            if data['item_type'] == 'resource':
                if data['type'] == 'header':
                    item_node = module_node.add_leaf(
                        Text(data['content'], 'markdown.h3'), data
                    )
                elif data['type'] == 'lecture':
                    data['description'] = ''
                    if data.get('video'):
                        youtube_url = f'https://www.youtube.com/watch?v={data["video"]}'
                        if data.get('playlist'):
                            youtube_url += f'&list={data["playlist"]}'
                        data['description'] += (
                            f'Video: [{youtube_url}]({youtube_url})\n\n'
                        )
                    if data.get('slides'):
                        slides_url = (
                            'https://docs.google.com/presentation/d/'
                            f'{data["slides"]}/embed'
                        )
                        data['description'] += (
                            f'Slides: [{slides_url}]({slides_url})\n\n'
                        )
                    item_node = module_node.add_leaf(
                        f'Lecture: {display_name(data, "resource")}', data
                    )
                elif data['type'] == 'markdown':
                    data['description'] = data['content']
                    item_node = module_node.add_leaf(
                        f'Resource: {display_name(data, "resource")}', data
                    )
            elif data['item_type'] == 'challenge':
                item_node = module_node.add_leaf(
                    f'Challenge: {display_name(data, "challenge")}', data
                )

            if item_node:
                self.node_index[self.data_key(data)] = item_node

    def load_dojo_modules(self, dojo_node) -> None:
        dojo_data = dojo_node.data
        if not dojo_data:
            return
        dojo_id = dojo_data['id']
        if dojo_id in self.loaded_modules:
            return
        modules = (
            request(f'/dojos/{dojo_id}/modules', auth=self.auth).json().get('modules')
        )
        for module in modules:
            self.store_module(dojo_id, module)
            module_data = self.data[dojo_id]['modules'][module['id']]
            self.add_module_node(dojo_node, module_data)
        self.loaded_modules.add(dojo_id)

    def populate_tree(self, tree: VimTree) -> None:
        tree.clear()
        tree.root.label = ROOT_LABEL
        tree.root.data = {'description': ROOT_DESCRIPTION}
        tree.root.expand()
        self.node_index = {}
        for dojo in self.data.values():
            dojo_node = tree.root.add(
                Text(f'Dojo: {display_name(dojo["data"], "dojo")}', 'markdown.h1'),
                dojo['data'],
                allow_expand=bool(dojo['modules'])
                or dojo['data'].get('modules_count', 0) > 0,
            )
            self.node_index[self.data_key(dojo['data'])] = dojo_node
            for module in dojo['modules'].values():
                self.add_module_node(dojo_node, module)

    def compose(self) -> ComposeResult:
        tree = VimTree(ROOT_LABEL, {'description': ROOT_DESCRIPTION}, id='tree')
        self.populate_tree(tree)

        with Horizontal():
            yield tree
            with Vertical():
                yield DescriptionViewer(show_table_of_contents=False, id='details')
                yield Static('Use the tree to browse challenges.', id='status')
        yield Footer()

    def on_mount(self) -> None:
        viewer = self.query_one('#details', DescriptionViewer)
        self.call_after_refresh(
            lambda: viewer.query_one(Markdown).update(ROOT_DESCRIPTION)
        )

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        data = event.node.data
        details = render_details(data, self.can_start)
        self.query_one('#details', DescriptionViewer).query_one(Markdown).update(
            details
        )
        status = self.query_one('#status', Static)
        if data and data.get('item_type') == 'challenge':
            status.update(
                'Enter opens the Standard / Privileged mode picker.'
                if self.can_start
                else 'Log in to start challenges.'
            )
        elif data and data.get('type') == 'header':
            status.update('Section heading.')
        elif data and data.get('item_type') == 'resource':
            status.update('Resource selected.')
        elif data and 'modules_count' in data:
            status.update('Expand the dojo to load its modules.')
        elif data and 'challenges' in data:
            status.update('Expand the module to browse its contents.')
        else:
            status.update('Use the tree to browse challenges.')

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        if event.node.data and event.node.data.get('modules_count') is not None:
            self.load_dojo_modules(event.node)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data or data.get('item_type') != 'challenge':
            return
        if not self.can_start:
            self.query_one('#status', Static).update('Log in to start challenges.')
            return
        dojo = self.data[data['_dojo_id']]['data']
        module = self.data[data['_dojo_id']]['modules'][data['_module_id']]['data']
        self.push_screen(StartChallengeModal(dojo, module, data))

    def capture_tree_state(self) -> tuple[tuple | None, set[tuple]]:
        tree = self.query_one('#tree', VimTree)
        selected = self.data_key(tree.cursor_node.data) if tree.cursor_node else None
        expanded = set()

        def collect(node) -> None:
            key = self.data_key(node.data)
            if key and node.is_expanded:
                expanded.add(key)
            for child in node.children:
                collect(child)

        collect(tree.root)
        return selected, expanded

    def restore_tree_state(self, selected: tuple | None, expanded: set[tuple]) -> None:
        tree = self.query_one('#tree', VimTree)
        order = {'dojo': 0, 'module': 1, 'resource': 2, 'challenge': 2}
        for key in sorted(expanded, key=lambda item: order[item[0]]):
            node = self.node_index.get(key)
            if node:
                node.expand()
        tree.get_node_at_line(tree.last_line)
        candidates = [selected] if selected else []
        if selected and selected[0] in ('resource', 'challenge'):
            candidates.append(('module', selected[1], selected[2]))
        if selected and selected[0] in ('module', 'resource', 'challenge'):
            candidates.append(('dojo', selected[1]))
        target = next(
            (self.node_index[key] for key in candidates if key in self.node_index),
            tree.root,
        )
        tree.move_cursor(target)

    def action_reload(self) -> None:
        status = self.query_one('#status', Static)
        status.update('Reloading catalog...')
        selected, expanded = self.capture_tree_state()
        old_data = self.data
        old_loaded_modules = self.loaded_modules
        try:
            self.load_catalog()
            dojo_ids = {
                key[1]
                for key in expanded | ({selected} if selected else set())
                if key[0] in ('dojo', 'module', 'resource', 'challenge')
            }
            for dojo_id in dojo_ids:
                dojo = self.data.get(dojo_id)
                if dojo and dojo_id not in self.loaded_modules:
                    self.load_initial_modules(dojo['data'])
        except SystemExit:
            self.data = old_data
            self.loaded_modules = old_loaded_modules
            status.update('Reload failed.')
            return
        except (KeyError, TypeError, ValueError) as exc:
            self.data = old_data
            self.loaded_modules = old_loaded_modules
            status.update(f'Reload failed: {exc}')
            return
        self.populate_tree(self.query_one('#tree', VimTree))
        self.restore_tree_state(selected, expanded)
        status.update('Catalog reloaded.')


def init_tree(
    path: str | None = None,
    dojo_id: str | None = None,
    module_id: str | None = None,
    challenge_id: str | None = None,
    auth: bool = False,
    public: bool = False,
    official: bool = False,
) -> bool:
    dojo_id, module_id, challenge_id = resolve_catalog_path(
        path, dojo_id, module_id, challenge_id
    )
    can_start = authentication_available()
    if auth and not can_start:
        error('Authentication is required; please log in or run this in the dojo.')
    use_auth = auth or (can_start and not public)
    app = TreeApp(
        dojo_id,
        module_id,
        challenge_id,
        use_auth,
        official,
        can_start,
    )
    return bool(app.run())
