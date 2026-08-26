"""Apply minimal structural edits to JSON with comments."""

import json
from dataclasses import dataclass


class JsoncEditError(ValueError):
    """Raised when JSONC cannot be parsed or safely edited."""


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    start: int
    end: int


@dataclass
class Node:
    kind: str
    start: int
    end: int
    open_end: int = 0
    close_start: int = 0
    content_end: int = 0
    trailing_comma: bool = False
    members: dict[str, Node] | None = None
    member_tokens: dict[str, Token] | None = None
    items: list[Node] | None = None
    value: object = None


def tokenize(source: str) -> list[Token]:
    """Tokenize JSONC while retaining source offsets."""
    tokens = []
    index = 0
    while index < len(source):
        character = source[index]
        if character.isspace():
            index += 1
            continue
        if source.startswith('//', index):
            newline = source.find('\n', index + 2)
            index = len(source) if newline == -1 else newline + 1
            continue
        if source.startswith('/*', index):
            end = source.find('*/', index + 2)
            if end == -1:
                raise JsoncEditError('Unterminated block comment.')
            index = end + 2
            continue
        if character in '{}[]:,':
            tokens.append(Token(character, character, index, index + 1))
            index += 1
            continue
        if character == '"':
            end = index + 1
            escaped = False
            while end < len(source):
                current = source[end]
                if current == '"' and not escaped:
                    end += 1
                    break
                if current == '\\' and not escaped:
                    escaped = True
                else:
                    escaped = False
                end += 1
            else:
                raise JsoncEditError('Unterminated string.')
            raw = source[index:end]
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise JsoncEditError(f'Invalid string at byte {index}: {exc.msg}.') from exc
            tokens.append(Token('string', value, index, end))
            index = end
            continue
        end = index
        while end < len(source) and not source[end].isspace() and source[end] not in '{}[]:,':
            if source.startswith('//', end) or source.startswith('/*', end):
                break
            end += 1
        raw = source[index:end]
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JsoncEditError(f'Invalid value at byte {index}: {exc.msg}.') from exc
        tokens.append(Token('value', value, index, end))
        index = end
    return tokens


class Parser:
    """Parse significant JSONC tokens into source-aware nodes."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def current(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self, kind: str | None = None) -> Token:
        token = self.current()
        if token is None:
            raise JsoncEditError('Unexpected end of settings.')
        if kind is not None and token.kind != kind:
            raise JsoncEditError(f'Expected {kind} at byte {token.start}.')
        self.index += 1
        return token

    def parse(self) -> Node:
        node = self.parse_value()
        if token := self.current():
            raise JsoncEditError(f'Unexpected token at byte {token.start}.')
        return node

    def parse_value(self) -> Node:
        token = self.current()
        if token is None:
            raise JsoncEditError('Expected a value.')
        if token.kind == '{':
            return self.parse_object()
        if token.kind == '[':
            return self.parse_array()
        token = self.take()
        if token.kind not in {'string', 'value'}:
            raise JsoncEditError(f'Expected a value at byte {token.start}.')
        return Node(token.kind, token.start, token.end, value=token.value)

    def parse_object(self) -> Node:
        opening = self.take('{')
        members = {}
        member_tokens = {}
        content_end = opening.end
        trailing_comma = False
        while (token := self.current()) is not None and token.kind != '}':
            key = self.take('string')
            if key.value in members:
                raise JsoncEditError(f'Duplicate key {key.value!r} at byte {key.start}.')
            self.take(':')
            value = self.parse_value()
            members[str(key.value)] = value
            member_tokens[str(key.value)] = key
            content_end = value.end
            token = self.current()
            if token is not None and token.kind == ',':
                comma = self.take(',')
                content_end = comma.end
                token = self.current()
                trailing_comma = token is not None and token.kind == '}'
            elif token is None or token.kind != '}':
                position = token.start if token else len(self.tokens)
                raise JsoncEditError(f'Expected comma at byte {position}.')
        closing = self.take('}')
        return Node(
            'object',
            opening.start,
            closing.end,
            opening.end,
            closing.start,
            content_end,
            trailing_comma,
            members,
            member_tokens,
        )

    def parse_array(self) -> Node:
        opening = self.take('[')
        items = []
        content_end = opening.end
        trailing_comma = False
        while (token := self.current()) is not None and token.kind != ']':
            value = self.parse_value()
            items.append(value)
            content_end = value.end
            token = self.current()
            if token is not None and token.kind == ',':
                comma = self.take(',')
                content_end = comma.end
                token = self.current()
                trailing_comma = token is not None and token.kind == ']'
            elif token is None or token.kind != ']':
                position = token.start if token else len(self.tokens)
                raise JsoncEditError(f'Expected comma at byte {position}.')
        closing = self.take(']')
        return Node('array', opening.start, closing.end, opening.end, closing.start, content_end, trailing_comma, items=items)


def line_indent(source: str, position: int) -> str:
    """Return indentation at a source position."""
    start = source.rfind('\n', 0, position) + 1
    line = source[start:position]
    return line[: len(line) - len(line.lstrip())]


def child_indent(source: str, node: Node) -> str:
    """Infer indentation for a child of an object or array."""
    positions = []
    if node.member_tokens:
        positions.extend(token.start for token in node.member_tokens.values())
    if node.items:
        positions.extend(item.start for item in node.items)
    if positions:
        indent = line_indent(source, min(positions))
        if indent:
            return indent
    return line_indent(source, node.close_start) + '  '


def render_value(value: object, indent: str) -> str:
    """Render a new JSON value at the requested indentation."""
    lines = json.dumps(value, ensure_ascii=False, indent=2).splitlines()
    return lines[0] + ''.join(f'\n{indent}{line}' for line in lines[1:])


def insert_member(source: str, node: Node, key: str, value: object) -> str:
    """Insert one object member without rewriting existing content."""
    if node.kind != 'object':
        raise JsoncEditError('Expected an object while traversing settings.')
    indent = child_indent(source, node)
    closing_indent = line_indent(source, node.close_start)
    rendered = render_value(value, indent)
    multiline = '\n' in source[node.open_end : node.close_start] or '\n' in rendered
    prefix = '' if not node.members or node.trailing_comma else ','
    if multiline:
        insertion_position = node.close_start - len(closing_indent)
        comma = prefix
        suffix = ',' if node.trailing_comma else ''
        insertion = f'{indent}{json.dumps(key)}: {rendered}{suffix}\n'
        return (
            source[: node.content_end]
            + comma
            + source[node.content_end : insertion_position]
            + insertion
            + source[insertion_position:]
        )
    else:
        separator = '' if not node.members else ' '
        insertion = f'{prefix}{separator}{json.dumps(key)}: {rendered}'
    return source[: node.content_end] + insertion + source[node.content_end :]


def node_value(node: Node) -> object:
    """Convert a parsed node into its Python value."""
    if node.kind == 'object':
        return {key: node_value(value) for key, value in (node.members or {}).items()}
    if node.kind == 'array':
        return [node_value(value) for value in node.items or []]
    return node.value


def append_items(source: str, node: Node, values: list[str] | list[object]) -> str:
    """Append values to an array without rewriting existing items."""
    if node.kind != 'array':
        raise JsoncEditError('Target setting must be an array.')
    existing = [node_value(item) for item in node.items or []]
    missing = [value for value in values if value not in existing]
    if not missing:
        return source
    indent = child_indent(source, node)
    closing_indent = line_indent(source, node.close_start)
    multiline = '\n' in source[node.open_end : node.close_start]
    prefix = '' if not node.items or node.trailing_comma else ','
    if multiline:
        body = f',\n{indent}'.join(render_value(value, indent) for value in missing)
        insertion_position = node.close_start - len(closing_indent)
        suffix = ',' if node.trailing_comma else ''
        insertion = f'{indent}{body}{suffix}\n'
        return (
            source[: node.content_end]
            + prefix
            + source[node.content_end : insertion_position]
            + insertion
            + source[insertion_position:]
        )
    else:
        separator = '' if not node.items else ' '
        body = ', '.join(render_value(value, indent) for value in missing)
        insertion = f'{prefix}{separator}{body}'
    return source[: node.content_end] + insertion + source[node.content_end :]


def append_array_values(source: str, path: tuple[str, ...], values: list[str]) -> str:
    """Append strings at a nested JSONC array path using one minimal edit."""
    if not path:
        raise JsoncEditError('Setting path cannot be empty.')
    root = Parser(tokenize(source)).parse()
    if root.kind != 'object':
        raise JsoncEditError('Zed settings must contain an object.')
    node = root
    for index, key in enumerate(path):
        if node.kind != 'object' or node.members is None:
            setting = '.'.join(path[:index])
            raise JsoncEditError(f'{setting} must be an object.')
        child = node.members.get(key)
        if child is None:
            value: object = values
            for missing_key in reversed(path[index + 1 :]):
                value = {missing_key: value}
            return insert_member(source, node, key, value)
        node = child
    if node.kind == 'array' and any(item.kind != 'string' for item in node.items or []):
        raise JsoncEditError('Target setting must contain only strings.')
    return append_items(source, node, values)


def append_array_items(source: str, path: tuple[str, ...], values: list[object]) -> str:
    """Append arbitrary JSON values at a nested array path."""
    if not path:
        raise JsoncEditError('Setting path cannot be empty.')
    root = Parser(tokenize(source)).parse()
    if root.kind != 'object':
        raise JsoncEditError('Zed settings must contain an object.')
    node = root
    for index, key in enumerate(path):
        if node.kind != 'object' or node.members is None:
            setting = '.'.join(path[:index])
            raise JsoncEditError(f'{setting} must be an object.')
        child = node.members.get(key)
        if child is None:
            value: object = values
            for missing_key in reversed(path[index + 1 :]):
                value = {missing_key: value}
            return insert_member(source, node, key, value)
        node = child
    return append_items(source, node, values)


def get_path_value(source: str, path: tuple[str, ...]) -> object:
    """Return a value from a JSONC document."""
    node = Parser(tokenize(source)).parse()
    for key in path:
        if node.kind != 'object' or node.members is None or key not in node.members:
            raise KeyError('.'.join(path))
        node = node.members[key]
    return node_value(node)
