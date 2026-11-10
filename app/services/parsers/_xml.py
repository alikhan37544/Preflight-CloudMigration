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


def _step_name(element: etree._Element) -> str:
    """Match lxml ``getpath`` step names, including namespace prefixes."""
    tag = element.tag
    if not isinstance(tag, str):
        return "*"
    qname = etree.QName(tag)
    if qname.namespace is None:
        return qname.localname
    prefix = element.prefix
    if prefix is None:
        # lxml uses a wildcard for default-namespace elements because a
        # prefix-less name would not resolve back to the same element.
        return "*"
    return f"{prefix}:{qname.localname}"


class XPathBuilder:
    """Build ``getpath``-equivalent paths with one sibling scan per parent.

    ``tree.getpath`` walks the same sibling axis for every call, which is
    quadratic for a wide screen. Widgets in one PCF share a parent, so the
    per-parent tag counts and indexes are computed once and reused.
    """

    __slots__ = ("tree", "_siblings")

    def __init__(self, tree: etree._ElementTree) -> None:
        self.tree = tree
        self._siblings: dict[etree._Element, dict[etree._Element, tuple[int, int]]] = {}

    def _sibling_index(self, element: etree._Element) -> tuple[int, int]:
        parent = element.getparent()
        assert parent is not None
        indexes = self._siblings.get(parent)
        if indexes is None:
            totals: dict[object, int] = {}
            for child in parent:
                if isinstance(child.tag, str):
                    totals[child.tag] = totals.get(child.tag, 0) + 1
            indexes = {}
            seen: dict[object, int] = {}
            for child in parent:
                if not isinstance(child.tag, str):
                    continue
                seen[child.tag] = seen.get(child.tag, 0) + 1
                indexes[child] = (seen[child.tag], totals[child.tag])
            self._siblings[parent] = indexes
        return indexes[element]

    def path(self, element: etree._Element) -> str:
        steps: list[str] = []
        node: etree._Element | None = element
        while node is not None:
            name = _step_name(node)
            parent = node.getparent()
            if parent is not None:
                index, total = self._sibling_index(node)
                if total > 1:
                    name = f"{name}[{index}]"
            steps.append(name)
            node = parent
        return "/" + "/".join(reversed(steps))


def xpath_with_index(tree: etree._ElementTree, element: etree._Element,
                     builder: XPathBuilder | None = None) -> str:
    path = (builder or XPathBuilder(tree)).path(element)
    last = path.rsplit("/", 1)[-1]
    if "[" not in last:
        path = f"{path}[1]"
    return path


def line_of(element: etree._Element) -> int:
    return int(element.sourceline or 1)


def excerpt(tree: etree._ElementTree, element: etree._Element) -> str:
    return etree.tostring(element, encoding="unicode", with_tail=False)
