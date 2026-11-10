"""Parser contract tests: XML artefacts, YAML line marks, Gosu masking.

Written before the parser implementations.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from lxml import etree

from app.services.parsers._xml import XPathBuilder, safe_parser, xpath_with_index
from app.services.parsers.config import parse_config_yaml, parse_json_with_pointer
from app.services.parsers.entity import parse_entity
from app.services.parsers.gosu import parse_gunit, scan_gosu
from app.services.parsers.pcf import parse_pcf
from app.services.parsers.product import parse_product_xml, parse_template_xml
from app.services.parsers.typelist import parse_typelist


def test_parse_pcf_widgets_and_lines(tiny_snapshot: Path) -> None:
    doc = parse_pcf(tiny_snapshot / "config/web/pcf/policy/PAVehicleDV.pcf")
    assert doc.name == "PAVehicleDV"
    assert [w.widget_type for w in doc.widgets] == ["TypeKeyInput", "TextInput", "TextInput"]
    assert [w.binding for w in doc.widgets] == ["VehicleType", "ModelYear", "GarageLocation_Ext"]
    assert all(w.line and w.line >= 1 for w in doc.widgets)
    assert doc.widgets[0].xpath.endswith("TypeKeyInput[1]")


def test_xpath_builder_matches_lxml_getpath_including_namespaces(tmp_path: Path) -> None:
    xml = (
        '<PCF xmlns:x="urn:prefixed" name="P">'
        "<Screen>"
        '<TextInput id="a"/><TextInput id="b"/>'
        '<x:TextInput id="c"/><TextInput id="d"/>'
        "<Other><TextInput id=\"e\"/></Other>"
        "</Screen>"
        "</PCF>"
    )
    path = tmp_path / "Namespaced.pcf"
    path.write_text(xml, encoding="utf-8")
    tree = etree.parse(str(path), safe_parser())
    builder = XPathBuilder(tree)
    for element in tree.iter():
        assert builder.path(element) == tree.getpath(element)

    # Default-namespace elements use lxml's wildcard step; prefixed elements
    # keep their prefix so tree.xpath() resolves the stored locator.
    default_xml = (
        '<PCF xmlns="urn:default"><Screen><TextInput id="a"/><TextInput id="b"/>'
        "</Screen></PCF>"
    )
    default_tree = etree.fromstring(default_xml).getroottree()
    default_builder = XPathBuilder(default_tree)
    widgets = [element for element in default_tree.iter() if element.get("id")]
    assert [default_builder.path(element) for element in widgets] == [
        "/*/*/*[1]", "/*/*/*[2]",
    ]
    for element in widgets:
        assert default_tree.xpath(default_builder.path(element))[0] == element


def test_parse_pcf_locator_paths_resolve_back_to_widgets(tiny_snapshot: Path) -> None:
    path = tiny_snapshot / "config/web/pcf/policy/PAVehicleDV.pcf"
    doc = parse_pcf(path)
    tree = etree.parse(str(path), safe_parser())
    for widget in doc.widgets:
        found = tree.xpath(widget.xpath)
        assert len(found) == 1
        assert found[0].get("id") == widget.widget_id


def test_parse_entity_columns_and_extension(tiny_snapshot: Path) -> None:
    base = parse_entity(tiny_snapshot / "config/metadata/entity/PersonalVehicle.eti")
    assert base.name == "PersonalVehicle"
    assert [c.name for c in base.columns] == ["ModelYear", "Make", "VIN", "Usage"]
    assert base.columns[3].type == "TypeKey"
    assert base.columns[3].typelist == "VehicleUsage"
    assert base.extension is False
    assert all(c.line and c.line >= 1 for c in base.columns)

    ext = parse_entity(tiny_snapshot / "config/extensions/entity/PersonalVehicle.etx")
    assert ext.extension is True
    assert [c.name for c in ext.columns] == ["GarageLocation_Ext", "Territory_Ext"]
    assert ext.columns[0].is_custom is True


def test_parse_typelist_and_extension(tiny_snapshot: Path) -> None:
    base = parse_typelist(tiny_snapshot / "config/metadata/typelist/VehicleType.tti")
    assert base.name == "VehicleType"
    assert [c.name for c in base.codes] == ["Passenger", "Trailer"]
    assert base.extension is False

    ext = parse_typelist(tiny_snapshot / "config/extensions/typelist/VehicleType.ttx")
    assert ext.extension is True
    assert [c.name for c in ext.codes] == ["Motorcycle_Ext"]
    assert ext.codes[0].is_custom is True
    assert ext.codes[0].line >= 1


def test_parse_product_xml_types(tiny_snapshot: Path) -> None:
    model = parse_product_xml(tiny_snapshot / "config/resources/productmodel/PersonalAuto.xml")
    assert model.name == "PersonalAuto"
    assert [t.name for t in model.types] == ["PAVehicle"]
    assert model.types[0].line >= 1


def test_parse_template_xml_fields(tmp_path: Path) -> None:
    path = tmp_path / "PersonalAutoTemplate.xml"
    path.write_text(
        """<?xml version="1.0"?>
<productTemplate name="PersonalAuto">
  <type name="PAVehicle">
    <field name="Year" type="Integer"/>
    <field name="VehicleType" type="TypeKey"/>
  </type>
  <type name="PersonalAutoRatingFactorConfiguration">
    <field name="Factor" type="Decimal"/>
  </type>
</productTemplate>
""",
        encoding="utf-8",
    )
    model = parse_template_xml(path)
    assert model.name == "PersonalAuto"
    by_name = {t.name: t for t in model.types}
    assert by_name["PAVehicle"].fields[0].name == "Year"
    assert by_name["PAVehicle"].fields[0].line >= 1
    assert len("PersonalAutoRatingFactorConfiguration") > 24


def test_parse_config_yaml_reports_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / "pa_codegen_config_ext-1.0.yaml"
    path.write_text(
        """types:
  PAVehicle:
    nameOverride: PersonalVehicle
    fields:
      Year:
        nameOverride: ModelYear
""",
        encoding="utf-8",
    )
    doc = parse_config_yaml(path)
    assert doc.data["types"]["PAVehicle"]["nameOverride"] == "PersonalVehicle"
    assert doc.line_for("types.PAVehicle.nameOverride") == 3
    assert doc.line_for("types.PAVehicle.fields.Year.nameOverride") == 6


def test_yaml_alias_bomb_is_rejected_quickly(tmp_path: Path) -> None:
    lines = ['a0: &a0 ["x","x","x","x","x","x","x","x","x","x"]']
    previous = "a0"
    for level in range(1, 8):
        current = f"a{level}"
        lines.append(f"{current}: &{current} [" + ",".join([f"*{previous}"] * 10) + "]")
        previous = current
    path = tmp_path / "alias-bomb.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(path.read_bytes()) < 1024

    started = time.monotonic()
    with pytest.raises(ValueError, match="alias"):
        parse_config_yaml(path)
    assert time.monotonic() - started < 1.0


def test_yaml_nesting_limit_is_enforced(tmp_path: Path) -> None:
    lines = []
    for level in range(70):
        lines.append("  " * level + f"level{level}:")
    lines.append("  " * 70 + "value: 1")
    path = tmp_path / "deep.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nesting limit"):
        parse_config_yaml(path)


def test_normal_yaml_with_anchors_but_no_aliases_still_parses(tmp_path: Path) -> None:
    path = tmp_path / "anchors.yaml"
    path.write_text("types: &types\n  PAVehicle:\n    nameOverride: PersonalVehicle\n",
                    encoding="utf-8")
    doc = parse_config_yaml(path)
    assert doc.data["types"]["PAVehicle"]["nameOverride"] == "PersonalVehicle"


def test_json_pointer_returns_value_and_excerpt(tmp_path: Path) -> None:
    path = tmp_path / "policyperiod_pa_ext-1.0.schema.json"
    path.write_text(
        '{\n  "properties": {\n    "vehicleType": {"type": "string"}\n  }\n}\n',
        encoding="utf-8",
    )
    value, excerpt = parse_json_with_pointer(path, "/properties/vehicleType")
    assert value == {"type": "string"}
    assert "vehicleType" in excerpt


def test_gosu_scanner_extracts_symbols_and_masks_comments(tmp_path: Path) -> None:
    path = tmp_path / "PersonalVehicleValidation.gs"
    path.write_text(
        """package acme.validation

uses gw.api.database.Query

class PersonalVehicleValidation {
  // Query.make(PersonalVehicle) in a comment must not be detected
  function validate(vehicle : PersonalVehicle) : String {
    var note = "java.sql.Connection in a string must not be detected"
    if (vehicle.ModelYear < 1900) {
      return "Invalid model year"
    }
    return null
  }
}
""",
        encoding="utf-8",
    )
    doc = scan_gosu(path)
    assert doc.package == "acme.validation"
    assert doc.imports == ["gw.api.database.Query"]
    assert [c.name for c in doc.classes] == ["PersonalVehicleValidation"]
    assert [m.name for m in doc.classes[0].methods] == ["validate"]
    assert "Query.make" not in doc.masked
    assert "java.sql.Connection" not in doc.masked
    assert "vehicle.ModelYear" in doc.masked
    assert "Query.make" in doc.raw


def test_gosu_scanner_brace_matching_for_commit(tmp_path: Path) -> None:
    path = tmp_path / "BundleCommit.gs"
    path.write_text(
        """package acme
class BundleCommit {
  function save() {
    gw.transaction.Transaction.runWithNewBundle(\\bundle -> {
      bundle.add(new PersonalVehicle())
      bundle.commit()
    })
  }
}
""",
        encoding="utf-8",
    )
    doc = scan_gosu(path)
    assert doc.find_blocks("runWithNewBundle")
    block = doc.find_blocks("runWithNewBundle")[0]
    assert "commit()" in block.text
    assert block.start_line <= block.commit_line <= block.end_line


def test_gunit_detects_db_calls(tmp_path: Path) -> None:
    path = tmp_path / "PersonalVehicleRatingDBTest.gs"
    path.write_text(
        """package acme
class PersonalVehicleRatingDBTest extends GUnitTestClassBase {
  function testRate() {
    var q = Query.make(PersonalVehicle)
    var rows = q.select().toList()
    loadSampleData()
  }
}
""",
        encoding="utf-8",
    )
    test = parse_gunit(path)
    assert test.class_name == "PersonalVehicleRatingDBTest"
    assert test.base_class == "GUnitTestClassBase"
    assert "Query.make" in test.db_calls
    assert "loadSampleData" in test.db_calls
    assert test.methods == ["testRate"]
