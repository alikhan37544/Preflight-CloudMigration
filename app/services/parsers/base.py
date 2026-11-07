"""Shared parsed-document dataclasses.

Parsers return plain dataclasses with source line numbers; services turn them
into Evidence records. No parser writes to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedWidget:
    widget_type: str
    widget_id: str
    binding: str
    xpath: str
    line: int = 1
    excerpt: str = ""


@dataclass
class ParsedPcf:
    name: str
    path: str
    widgets: list[ParsedWidget] = field(default_factory=list)


@dataclass
class ParsedColumn:
    name: str
    type: str
    line: int
    xpath: str
    typelist: str | None = None
    is_custom: bool = False
    excerpt: str = ""


@dataclass
class ParsedEntity:
    name: str
    path: str
    extension: bool
    columns: list[ParsedColumn] = field(default_factory=list)


@dataclass
class ParsedCode:
    name: str
    line: int
    xpath: str
    is_custom: bool = False
    excerpt: str = ""


@dataclass
class ParsedTypelist:
    name: str
    path: str
    extension: bool
    codes: list[ParsedCode] = field(default_factory=list)


@dataclass
class ParsedField:
    name: str
    type: str
    line: int
    xpath: str
    excerpt: str = ""


@dataclass
class ParsedType:
    name: str
    line: int
    xpath: str
    fields: list[ParsedField] = field(default_factory=list)
    excerpt: str = ""


@dataclass
class ParsedProduct:
    name: str
    path: str
    types: list[ParsedType] = field(default_factory=list)


@dataclass
class ParsedConfig:
    path: str
    data: dict
    line_index: dict[str, int] = field(default_factory=dict)

    def line_for(self, dotted: str) -> int | None:
        return self.line_index.get(dotted)


@dataclass
class GosuMethod:
    name: str
    line: int


@dataclass
class GosuClass:
    name: str
    base: str | None
    line: int
    methods: list[GosuMethod] = field(default_factory=list)


@dataclass
class GosuBlock:
    call: str
    start_line: int
    end_line: int
    commit_line: int | None
    text: str
    commit_lines: list[int] = field(default_factory=list)


@dataclass
class ParsedGosu:
    path: str
    package: str | None
    imports: list[str]
    raw: str
    masked: str
    classes: list[GosuClass]
    calls: list[str] = field(default_factory=list)
    blocks: list[GosuBlock] = field(default_factory=list)

    def find_blocks(self, needle: str) -> list[GosuBlock]:
        return [block for block in self.blocks if needle in block.call]


@dataclass
class ParsedGUnit:
    path: str
    class_name: str
    base_class: str | None
    methods: list[str]
    db_calls: list[str]
