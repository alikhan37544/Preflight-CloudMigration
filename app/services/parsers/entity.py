"""Entity metadata parser for .eti and .etx files."""

from __future__ import annotations

from pathlib import Path

from app.services.parsers._xml import excerpt as xml_excerpt, line_of, parse_file, xpath_with_index
from app.services.parsers.base import ParsedColumn, ParsedEntity


def parse_entity(path: Path) -> ParsedEntity:
    tree = parse_file(path)
    root = tree.getroot()
    local = root.tag.rsplit("}", 1)[-1]
    extension = local.lower().endswith("extension") or str(path).lower().endswith(".etx")
    name = root.get("name") or Path(path).stem
    doc = ParsedEntity(name=name, path=str(path), extension=extension)
    for element in root.iter():
        tag = element.tag if isinstance(element.tag, str) else ""
        if tag.rsplit("}", 1)[-1] != "column":
            continue
        field_name = element.get("name")
        if not field_name:
            continue
        doc.columns.append(
            ParsedColumn(
                name=field_name,
                type=element.get("type") or "Unknown",
                typelist=element.get("typelist"),
                line=line_of(element),
                xpath=xpath_with_index(tree, element),
                is_custom=extension or field_name.endswith("_Ext"),
                excerpt=xml_excerpt(tree, element).strip(),
            )
        )
    return doc
