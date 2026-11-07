"""Safe XML parsing helpers shared by PCF/entity/typelist/product parsers."""

from __future__ import annotations

from lxml import etree

WIDGET_TAGS = {
    "TextInput", "TypeKeyInput", "RangeInput", "DropdownInput", "DateInput",
    "CheckBox", "RadioButton", "BooleanRadioInput", "CurrencyInput",
    "IntegerInput", "DecimalInput", "TextArea", "ListView", "DetailViewPanel",
}


def safe_parser(*, recover: bool = False) -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        recover=recover,
        remove_comments=False,
    )


def parse_file(path) -> etree._ElementTree:
    return etree.parse(str(path), safe_parser())


def xpath_with_index(tree: etree._ElementTree, element: etree._Element) -> str:
    path = tree.getpath(element)
    last = path.rsplit("/", 1)[-1]
    if "[" not in last:
        path = f"{path}[1]"
    return path


def line_of(element: etree._Element) -> int:
    return int(element.sourceline or 1)


def excerpt(tree: etree._ElementTree, element: etree._Element) -> str:
    return etree.tostring(element, encoding="unicode", with_tail=False)
