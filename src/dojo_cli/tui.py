"""Implements the custom Trogon TUI for the pwn.college dojo CLI."""

# TODO: rename to trogon_tui.py or something when/if I add more TUIs

import click
from cyclopts import App as CycloptsApp
import inspect
from pathlib import Path
import re
from rich.console import Group
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Button, Checkbox, ContentSwitcher, Input, Label, Static, Tab, Tabs
from textual.widgets.tree import TreeNode

from trogon.detect_run_string import detect_run_string
from trogon.introspect import ArgumentSchema, MultiValueParamData, OptionSchema
from trogon.trogon import (
    CommandBuilder,
    CommandForm,
    CommandInfo,
    CommandSchema,
    Trogon
)
from trogon.widgets.command_info import CommandMetadata
from trogon.widgets.multiple_choice import NonFocusableVerticalScroll
from trogon.widgets.parameter_controls import (
    ControlGroup,
    ControlGroupsContainer,
    ControlWidgetType,
    ParameterControls,
    ValueNotSupplied
)
from typing import Any, Callable, Iterable, Optional, get_args, get_origin

# The default checkbox values were blue X for unchecked and green X for checked, not good for colorblind users.
class CustomCheckbox(Checkbox):
    BUTTON_LEFT: str = '['
    BUTTON_INNER_OFF: str = ' '
    BUTTON_INNER_ON: str = '✓'
    BUTTON_RIGHT: str = ']'

    @property
    def _button(self) -> Content:
        button_value = self.BUTTON_INNER_ON if self.value else self.BUTTON_INNER_OFF
        button_style = self.get_visual_style('toggle--button')
        return Content.assemble(
            (self.BUTTON_LEFT + button_value + self.BUTTON_RIGHT, button_style)
        )

def normalize_markdown(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return inspect.cleandoc(text).strip()

def markdown_summary(text: Optional[str]) -> str:
    text = normalize_markdown(text) or ''
    return re.split(r'\n\s*\n', text, maxsplit=1)[0].strip()

def render_markdown(text: Optional[str]) -> RichMarkdown:
    return RichMarkdown(normalize_markdown(text) or '')

class CustomParameterControls(ParameterControls):
    def apply_filter(self, filter_query: str) -> bool:
        help_text = getattr(self.schema, 'help', '') or ''

        if not filter_query:
            should_be_visible = True
            self.display = True
            if help_text:
                try:
                    help_label = self.query_one('.command-form-control-help-text', Static)
                    help_label.update(render_markdown(help_text))
                except NoMatches:
                    pass
            return should_be_visible

        name = self.schema.name
        if isinstance(name, str):
            should_be_visible = filter_query in name.casefold()
        else:
            name_contains_query = any(filter_query in name.casefold() for name in self.schema.name)
            help_contains_query = filter_query in help_text.casefold()
            should_be_visible = name_contains_query or help_contains_query

        self.display = should_be_visible

        if help_text:
            try:
                help_label = self.query_one('.command-form-control-help-text', Static)
                new_help_text = Text(help_text)
                new_help_text.highlight_words(filter_query.split(), 'black on yellow', case_sensitive=False)
                help_label.update(new_help_text)
            except NoMatches:
                pass

        return should_be_visible

    def compose(self) -> ComposeResult:
        schema = self.schema
        name = schema.name
        argument_type = schema.type
        default = schema.default
        help_text = getattr(schema, 'help', '') or ''
        multiple = schema.multiple
        is_option = isinstance(schema, OptionSchema)
        nargs = schema.nargs

        assert isinstance(argument_type, click.types.ParamType)
        label = self._make_command_form_control_label(
            name, argument_type, is_option, schema.required, multiple=multiple
        )
        first_focus_control: Optional[Widget] = None

        with ControlGroupsContainer():
            # See https://github.com/Textualize/trogon/pull/123
            if not isinstance(argument_type, click.types.BoolParamType):
                yield Label(label, classes='command-form-label')

            if isinstance(argument_type, click.Choice) and multiple:
                control_method = self.get_control_method(argument_type)
                multiple_choice_widget = control_method(
                    default=default,
                    label=label,
                    multiple=multiple,
                    schema=schema,
                    control_id=schema.key,
                )
                yield from multiple_choice_widget
            else:
                assert default
                for default_value_tuple in default.values:
                    widget_group = list(self.make_widget_group())
                    with ControlGroup() as control_group:
                        if len(widget_group) == 1:
                            control_group.add_class('single-item')

                        for default_value, control_widget in zip(
                            default_value_tuple, widget_group
                        ):
                            self._apply_default_value(control_widget, default_value)
                            yield control_widget
                            if first_focus_control is None:
                                first_focus_control = control_widget

                if multiple or not default.values:
                    widget_group = list(self.make_widget_group())
                    with ControlGroup() as control_group:
                        if len(widget_group) == 1:
                            control_group.add_class('single-item')

                        for control_widget in widget_group:
                            yield control_widget
                            if first_focus_control is None:
                                first_focus_control = control_widget

        if self.first_control is None:
            self.first_control = first_focus_control

        if (multiple or nargs == -1) and not isinstance(argument_type, click.Choice):
            with Horizontal(classes='add-another-button-container'):
                yield Button('+ value', variant='success', classes='add-another-button')

        if help_text:
            yield Static(render_markdown(help_text), classes='command-form-control-help-text')

    def get_control_method(self, argument_type: Any) -> Callable:
        # See https://github.com/Textualize/trogon/pull/123
        if isinstance(argument_type, click.types.BoolParamType):
            return self.make_checkbox_control
        return super().get_control_method(argument_type)

    @staticmethod
    def make_checkbox_control(
        default: MultiValueParamData,
        label: Optional[Text],
        multiple: bool,
        schema: OptionSchema | ArgumentSchema,
        control_id: str,
    ) -> Iterable[ControlWidgetType]:
        control = CustomCheckbox(
            label or '',
            button_first=True,
            classes=f'command-form-checkbox {control_id}',
            value=bool(default.values[0][0] if default.values else ValueNotSupplied()),
        )
        yield control
        return control


class CustomCommandForm(CommandForm):
    def compose(self) -> ComposeResult:
        assert self.command_schema
        path_from_root = iter(reversed(self.command_schema.path_from_root))
        command_node = next(path_from_root)
        with VerticalScroll() as vs:
            vs.can_focus = False

            yield Input(
                placeholder='Search...',
                classes='command-form-filter-input',
                id='search',
            )

            while command_node is not None:
                options = command_node.options
                arguments = command_node.arguments
                if options or arguments:
                    with Vertical(
                        classes='command-form-command-group', id=command_node.key
                    ) as v:
                        is_inherited = command_node is not self.command_schema
                        prefix = '↪ ' if is_inherited else ''
                        v.border_title = f'{prefix}{command_node.name}'
                        if is_inherited:
                            assert v.border_title
                            v.border_title += ' [dim not bold](inherited)'
                        if arguments:
                            yield Label('Arguments', classes='command-form-heading')
                            for argument in arguments:
                                controls = CustomParameterControls(
                                    argument, id=argument.key
                                )
                                if self.first_control is None:
                                    self.first_control = controls
                                yield controls

                        if options:
                            yield Label('Options', classes='command-form-heading')
                            for option in options:
                                controls = CustomParameterControls(
                                    option, id=option.key
                                )
                                if self.first_control is None:
                                    self.first_control = controls
                                yield controls

                command_node = next(path_from_root, None)

class CustomCommandBuilder(CommandBuilder):
    def _update_command_description(self, command: CommandSchema) -> None:
        description_box = self.query_one('#home-command-description', Static)
        description_text = markdown_summary(command.docstring)
        description_box.update(
            Group(
                Text(command.name, style='bold'),
                render_markdown(description_text) if description_text else Text('No description available', style='dim'),
            )
        )

    async def _update_form_body(self, node: TreeNode[CommandSchema]) -> None:
        parent = self.query_one('#home-body-scroll', VerticalScroll)
        for child in parent.children:
            await child.remove()
        command_schema = node.data
        command_form = CustomCommandForm(
            command_schema=command_schema, command_schemas=self.command_schemas
        )
        await parent.mount(command_form)
        if not self.is_grouped_cli:
            command_form.focus()

class CustomTrogon(Trogon):
    # See https://github.com/Textualize/trogon/pull/120
    def action_show_command_info(self) -> None:
        command_form = self.query_one(CustomCommandForm)
        assert command_form.command_schema
        self.push_screen(CustomCommandInfo(command_form.command_schema))

    def get_default_screen(self) -> CustomCommandBuilder:
        return CustomCommandBuilder(self.cli, self.app_name, self.command_name)

class CustomCommandInfo(CommandInfo):
    def compose(self) -> ComposeResult:
        schema = self.command_schema
        path = schema.path_from_root
        path_string = ' ➜ '.join(command.name for command in path)

        title_style = self.get_component_rich_style('title')
        subtitle_style = self.get_component_rich_style('subtitle')
        modal_header = Text.assemble(
            (path_string, title_style), '\n', ('command info', subtitle_style)
        )

        with NonFocusableVerticalScroll(classes='command-info-container'):
            with Vertical(classes='command-info-header'):
                yield Static(modal_header, classes='command-info-header-text')
                tabs = Tabs(
                    Tab('Description', id='command-info-text'),
                    Tab('Metadata', id='command-info-metadata'),
                    classes='command-info-tabs',
                )
                tabs.focus()
                yield tabs

            command_info = normalize_markdown(self.command_schema.docstring) or 'No description available'

            with ContentSwitcher(initial='command-info-text', id='command-info-switcher'):
                yield Static(
                    render_markdown(command_info),
                    id='command-info-text',
                    classes='command-info-text',
                )
                yield CommandMetadata(
                    command_schema=self.command_schema,
                    id='command-info-metadata',
                    classes='command-info-metadata',
                )

def default_for(argument) -> Optional[Any]:
    default = argument.field_info.default
    if default is argument.field_info.empty:
        return None
    return default

def unwrap_hint(hint: Any) -> Any:
    origin = get_origin(hint)
    if origin is None:
        return hint

    args = [arg for arg in get_args(hint) if arg is not None and arg is not type(None)]
    if len(args) == 1:
        return unwrap_hint(args[0])

    return hint

def click_type_for(argument) -> click.ParamType:
    if choices := argument.get_choices(force=True):
        return click.Choice(list(choices))

    hint = unwrap_hint(argument.hint)
    origin = get_origin(hint)
    if origin is not None:
        return click.STRING

    if hint is bool:
        return click.BOOL
    if hint is int:
        return click.INT
    if hint is float:
        return click.FLOAT
    if hint is Path:
        return click.Path(path_type=Path)

    return click.STRING

def is_positional(argument) -> bool:
    field_info = argument.field_info
    return (
        field_info.kind in (field_info.POSITIONAL_ONLY, field_info.VAR_POSITIONAL)
        or argument.index is not None
    )

def option_decls(argument) -> list[str]:
    names = list(argument.parameter.name or ())
    negatives = list(argument.negatives)

    if not argument.is_flag() or not negatives:
        return names

    positive_long = next((name for name in names if name.startswith('--')), None)
    negative_long = next((name for name in negatives if name.startswith('--')), None)
    if positive_long and negative_long:
        return [
            f'{positive_long}/{negative_long}',
            *[name for name in names if name != positive_long],
        ]

    return [*names, *negatives]

def build_click_argument(argument) -> click.Argument:
    token_count, consume_all = argument.token_count()
    kwargs: dict[str, Any] = {
        'required': argument.required,
        'type': click_type_for(argument),
        'default': default_for(argument),
    }
    if consume_all:
        kwargs['nargs'] = -1
    elif token_count not in (0, 1):
        kwargs['nargs'] = token_count

    return click.Argument([argument.field_info.name], **kwargs)

def build_click_option(argument) -> click.Option:
    token_count, consume_all = argument.token_count()
    kwargs: dict[str, Any] = {
        'help': normalize_markdown(argument.parameter.help),
        'type': click_type_for(argument),
        'required': argument.required,
        'default': default_for(argument),
    }

    if argument.is_flag():
        kwargs['is_flag'] = True
        kwargs['required'] = False
    elif consume_all:
        kwargs['nargs'] = -1
    elif token_count not in (0, 1):
        kwargs['nargs'] = token_count

    return click.Option(option_decls(argument), **kwargs)

def build_click_params(app: CycloptsApp) -> list[click.Parameter]:
    if app.default_command is None:
        return []

    arguments = [
        argument
        for argument in app.assemble_argument_collection(parse_docstring=True)
        if argument.show
    ]
    params: list[click.Parameter] = []

    for argument in arguments:
        if is_positional(argument):
            params.append(build_click_argument(argument))

    for argument in arguments:
        if not is_positional(argument):
            params.append(build_click_option(argument))

    return params

def iter_visible_commands(app: CycloptsApp) -> Iterable[tuple[str, CycloptsApp]]:
    hidden_names = {*app.help_flags, *app.version_flags}
    for command_name in app:
        if command_name in hidden_names:
            continue

        command_app = app[command_name]
        if not command_app.show:
            continue

        yield command_name, command_app

def build_click_proxy(app: CycloptsApp, command_name: Optional[str] = None) -> click.Command | click.Group:
    subcommands = list(iter_visible_commands(app))
    params = build_click_params(app)
    help_text = normalize_markdown(app.help) or None

    if subcommands:
        group = click.Group(
            name=command_name,
            callback=app.default_command,
            help=help_text,
            params=params,
            invoke_without_command=app.default_command is not None,
        )
        for subcommand_name, subcommand_app in subcommands:
            group.add_command(
                build_click_proxy(subcommand_app, subcommand_name),
                name=subcommand_name,
            )
        return group

    return click.Command(
        name=command_name,
        callback=app.default_command,
        help=help_text,
        params=params,
    )

def init_trogon(app: CycloptsApp):
    tui = CustomTrogon(build_click_proxy(app), app_name=detect_run_string())
    tui.run()
