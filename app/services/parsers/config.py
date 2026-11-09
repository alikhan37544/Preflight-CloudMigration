"""YAML and JSON config parsers with source-line support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError
from ruamel.yaml.tokens import AliasToken, TagToken

# Bounds applied before the recursive line-index walk. Configuration files are
# small; anything beyond these limits is treated as hostile input.
MAX_YAML_NODES = 100_000
MAX_YAML_DEPTH = 64


def _guard_yaml_tree(data: Any) -> None:
    """Reject alias-expanded or deeply nested documents before walking them."""
    nodes = 0
    stack: list[tuple[Any, int]] = [(data, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_YAML_NODES:
            raise ValueError(
                f"YAML document exceeds the node limit ({MAX_YAML_NODES})"
            )
        if depth > MAX_YAML_DEPTH:
            raise ValueError(
                f"YAML document exceeds the nesting limit ({MAX_YAML_DEPTH})"
            )
        if isinstance(node, dict):
            stack.extend((value, depth + 1) for value in node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend((value, depth + 1) for value in node)


def _load_yaml_text(raw: str) -> Any:
    """Load YAML while rejecting explicit tags and alias expansion.

    Scanning tokens first catches ``!!python/...``, single-``!`` tags,
    verbatim ``!<...>`` tags, and aliases. Aliases are rejected because a small
    anchor/alias bomb expands exponentially when the parsed tree is walked.
    """
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    try:
        for token in yaml.scan(raw):
            if isinstance(token, TagToken):
                raise ValueError("YAML tags are not allowed in configuration files")
            if isinstance(token, AliasToken):
                raise ValueError("YAML aliases are not allowed in configuration files")
        data = yaml.load(raw)
    except YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    _guard_yaml_tree(data)
    return data


def parse_config_yaml(path: Path) -> "ParsedConfig":
    from app.services.parsers.base import ParsedConfig

    raw = Path(path).read_text(encoding="utf-8")
    data = _load_yaml_text(raw)
    if data is None:
        data = {}
    if not isinstance(data, (CommentedMap, dict)):
        raise ValueError("configuration root must be a mapping")

    line_index: dict[str, int] = {}

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, CommentedMap):
            for key in node.keys():
                dotted = f"{prefix}.{key}" if prefix else str(key)
                try:
                    key_line = node.lc.key(key)[0] + 1
                except Exception:
                    key_line = 0
                line_index[dotted] = key_line
                walk(node[key], dotted)
        elif isinstance(node, CommentedSeq):
            for index, item in enumerate(node):
                walk(item, f"{prefix}[{index}]")

    walk(data, "")
    return ParsedConfig(path=str(path), data=data, line_index=line_index)


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return document
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with '/'")
    current = document
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def parse_json_with_pointer(path: Path, pointer: str) -> tuple[Any, str]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    value = _resolve_pointer(document, pointer)
    key = pointer.rstrip("/").rsplit("/", 1)[-1]
    excerpt = json.dumps({key: value}, ensure_ascii=False)
    return value, excerpt


def config_value(doc, dotted: str) -> Any:
    current = doc.data
    for part in dotted.split("."):
        if isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(dotted)
    return current
