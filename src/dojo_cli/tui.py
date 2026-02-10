"""
Implements the custom Trogon TUI for the pwn.college dojo CLI.
"""

import click

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Label, Input, Static
from textual.widgets.tree import TreeNode

from trogon.introspect import ArgumentSchema, MultiValueParamData, OptionSchema
from trogon.trogon import CommandBuilder, CommandForm, CommandInfo, CommandSchema, Trogon
from trogon.widgets.parameter_controls import (
    ControlGroup, ControlGroupsContainer, ControlWidgetType,
    ParameterControls, ValueNotSupplied
)

from typer.main import get_group
from typing import Any, Callable, Iterable

# The default checkbox values were blue X for unchecked and green X for checked, not good for colorblind users.
class CustomCheckbox(Checkbox):
    BUTTON_LEFT: str = "["
    BUTTON_INNER_OFF: str = " "
    BUTTON_INNER_ON: str = "✓"
    BUTTON_RIGHT: str = "]"

    @property
    def _button(self) -> Content:
        button_value = self.BUTTON_INNER_ON if self.value else self.BUTTON_INNER_OFF
        button_style = self.get_visual_style("toggle--button")
        return Content.assemble((self.BUTTON_LEFT + button_value + self.BUTTON_RIGHT, button_style))

class CustomParameterControls(ParameterControls):
    def compose(self) -> ComposeResult:
        schema = self.schema
        name = schema.name
        argument_type = schema.type
        default = schema.default
        help_text = getattr(schema, "help", "") or ""
        multiple = schema.multiple
        is_option = isinstance(schema, OptionSchema)
        nargs = schema.nargs

        assert isinstance(argument_type, click.types.ParamType)
        label = self._make_command_form_control_label(
            name, argument_type, is_option, schema.required, multiple=multiple
        )
        first_focus_control: Widget | None = None

        with ControlGroupsContainer():
            # See https://github.com/Textualize/trogon/pull/123
            if not isinstance(argument_type, click.types.BoolParamType):
                yield Label(label, classes="command-form-label")

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
                            control_group.add_class("single-item")

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
                            control_group.add_class("single-item")

                        for control_widget in widget_group:
                            yield control_widget
                            if first_focus_control is None:
                                first_focus_control = control_widget

        if self.first_control is None:
            self.first_control = first_focus_control

        if (multiple or nargs == -1) and not isinstance(argument_type, click.Choice):
            with Horizontal(classes="add-another-button-container"):
                yield Button("+ value", variant="success", classes="add-another-button")

        if help_text:
            yield Static(help_text, classes="command-form-control-help-text")

    def get_control_method(self, argument_type: Any) -> Callable:
        # See https://github.com/Textualize/trogon/pull/123
        if isinstance(argument_type, click.types.BoolParamType):
            return self.make_checkbox_control
        return super().get_control_method(argument_type)

    @staticmethod
    def make_checkbox_control(
        default: MultiValueParamData,
        label: Text | None,
        multiple: bool,
        schema: OptionSchema | ArgumentSchema,
        control_id: str,
    ) -> Iterable[ControlWidgetType]:
        control = CustomCheckbox(
            label or "",
            button_first=True,
            classes=f"command-form-checkbox {control_id}",
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
                placeholder="Search...",
                classes="command-form-filter-input",
                id="search",
            )

            while command_node is not None:
                options = command_node.options
                arguments = command_node.arguments
                if options or arguments:
                    with Vertical(
                        classes="command-form-command-group", id=command_node.key
                    ) as v:
                        is_inherited = command_node is not self.command_schema
                        v.border_title = (
                            f"{'↪ ' if is_inherited else ''}{command_node.name}"
                        )
                        if is_inherited:
                            assert v.border_title
                            v.border_title += " [dim not bold](inherited)"
                        if arguments:
                            yield Label("Arguments", classes="command-form-heading")
                            for argument in arguments:
                                controls = CustomParameterControls(argument, id=argument.key)
                                if self.first_control is None:
                                    self.first_control = controls
                                yield controls

                        if options:
                            yield Label("Options", classes="command-form-heading")
                            for option in options:
                                controls = CustomParameterControls(option, id=option.key)
                                if self.first_control is None:
                                    self.first_control = controls
                                yield controls

                command_node = next(path_from_root, None)

class CustomCommandBuilder(CommandBuilder):
    async def _update_form_body(self, node: TreeNode[CommandSchema]) -> None:
        parent = self.query_one("#home-body-scroll", VerticalScroll)
        for child in parent.children:
            await child.remove()
        command_schema = node.data
        command_form = CustomCommandForm(command_schema=command_schema, command_schemas=self.command_schemas)
        await parent.mount(command_form)
        if not self.is_grouped_cli:
            command_form.focus()

class CustomTrogon(Trogon):
    # See https://github.com/Textualize/trogon/pull/120
    def action_show_command_info(self) -> None:
        command_form = self.query_one(CustomCommandForm)
        assert command_form.command_schema
        self.push_screen(CommandInfo(command_form.command_schema))

    def get_default_screen(self) -> CustomCommandBuilder:
        return CustomCommandBuilder(self.cli, self.app_name, self.command_name)

def init_tui(app):
    tui = CustomTrogon(get_group(app), click_context=click.get_current_context())
    tui.run()
