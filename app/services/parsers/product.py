"""Legacy product-model XML and extracted APD template XML parsers."""

from __future__ import annotations

from pathlib import Path

from app.services.parsers._xml import excerpt as xml_excerpt, line_of, parse_file, xpath_with_index
from app.services.parsers.base import ParsedField, ParsedProduct, ParsedType


def _parse_types(path: Path) -> ParsedProduct:
    tree = parse_file(path)
    root = tree.getroot()
    name = root.get("name") or Path(path).stem
    doc = ParsedProduct(name=name, path=str(path))
    for element in root.iter():
        tag = element.tag if isinstance(element.tag, str) else ""
        local = tag.rsplit("}", 1)[-1]
        if local not in {"type", "riskobject", "coverage", "line"}:
            continue
        type_name = element.get("name")
        if not type_name:
            continue
        parsed_type = ParsedType(
            name=type_name,
            line=line_of(element),
            xpath=xpath_with_index(tree, element),
            excerpt=xml_excerpt(tree, element).strip(),
        )
        for field_element in element:
            field_tag = field_element.tag if isinstance(field_element.tag, str) else ""
            if field_tag.rsplit("}", 1)[-1] not in {"field", "attribute", "column"}:
                continue
            field_name = field_element.get("name")
            if not field_name:
                continue
            parsed_type.fields.append(
                ParsedField(
                    name=field_name,
                    type=field_element.get("type") or "Unknown",
                    line=line_of(field_element),
                    xpath=xpath_with_index(tree, field_element),
                    excerpt=xml_excerpt(tree, field_element).strip(),
                )
            )
        doc.types.append(parsed_type)
    return doc


def parse_product_xml(path: Path) -> ParsedProduct:
    return _parse_types(path)


def parse_template_xml(path: Path) -> ParsedProduct:
    return _parse_types(path)
