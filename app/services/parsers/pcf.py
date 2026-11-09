"""PCF (Page Configuration File) parser.

PCF is XML. Widget XPaths and source lines are preserved as evidence locators.
No XSD validation is attempted or claimed.
"""

from __future__ import annotations

from pathlib import Path

from app.services.parsers._xml import (
    WIDGET_TAGS,
    XPathBuilder,
    excerpt as xml_excerpt,
    line_of,
    parse_file,
    xpath_with_index,
)
from app.services.parsers.base import ParsedPcf, ParsedWidget


def parse_pcf(path: Path) -> ParsedPcf:
    tree = parse_file(path)
    root = tree.getroot()
    builder = XPathBuilder(tree)
    name = root.get("name") or Path(path).stem
    doc = ParsedPcf(name=name, path=str(path))
    for element in root.iter():
        tag = element.tag if isinstance(element.tag, str) else ""
        local = tag.rsplit("}", 1)[-1]
        if local not in WIDGET_TAGS:
            continue
        if element is root:
            continue
        binding = element.get("value") or element.get("binding") or element.get("id") or ""
        widget_id = element.get("id") or binding or local
        doc.widgets.append(
            ParsedWidget(
                widget_type=local,
                widget_id=widget_id,
                binding=binding,
                xpath=xpath_with_index(tree, element, builder=builder),
                line=line_of(element),
                excerpt=xml_excerpt(tree, element).strip(),
            )
        )
    return doc


def widget_excerpt(path: Path, xpath: str) -> tuple[int, str]:
    tree = parse_file(path)
    elements = tree.xpath(xpath)
    if not elements:
        return 1, ""
    element = elements[0]
    return line_of(element), xml_excerpt(tree, element).strip()
