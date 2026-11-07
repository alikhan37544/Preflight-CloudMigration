"""Typelist metadata parser for .tti and .ttx files."""

from __future__ import annotations

from pathlib import Path

from app.services.parsers._xml import excerpt as xml_excerpt, line_of, parse_file, xpath_with_index
from app.services.parsers.base import ParsedCode, ParsedTypelist


def parse_typelist(path: Path) -> ParsedTypelist:
    tree = parse_file(path)
    root = tree.getroot()
    local = root.tag.rsplit("}", 1)[-1]
    extension = local.lower().endswith("extension") or str(path).lower().endswith(".ttx")
    name = root.get("name") or Path(path).stem
    doc = ParsedTypelist(name=name, path=str(path), extension=extension)
    for element in root.iter():
        tag = element.tag if isinstance(element.tag, str) else ""
        if tag.rsplit("}", 1)[-1] != "code":
            continue
        code_name = element.get("name")
        if not code_name:
            continue
        doc.codes.append(
            ParsedCode(
                name=code_name,
                line=line_of(element),
                xpath=xpath_with_index(tree, element),
                is_custom=extension or code_name.endswith("_Ext"),
                excerpt=xml_excerpt(tree, element).strip(),
            )
        )
    return doc
