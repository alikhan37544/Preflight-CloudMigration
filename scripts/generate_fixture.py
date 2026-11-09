"""Generate PreFlight's synthetic Guidewire-style estates and ground truth.

Everything here is synthetic. No customer data, no confidential Guidewire
content. File counts are deterministic so tests can assert exact manifests.

Usage:
    python scripts/generate_fixture.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures"
GROUND = REPO / "ground_truth"

MAIN_FILES = 650
DEMO_FILES = 300
HOLDOUT_FILES = 150


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def entity_xml(name: str, fields: list[tuple[str, str, str | None]]) -> str:
    rows = []
    for field_name, field_type, typelist in fields:
        attrs = f'name="{field_name}" type="{field_type}"'
        if typelist:
            attrs += f' typelist="{typelist}"'
        rows.append(f"  <column {attrs}/>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<entity name="{name}">\n' + "\n".join(rows) + "\n</entity>\n"
    )


def entity_ext_xml(name: str, fields: list[tuple[str, str, str | None]]) -> str:
    rows = []
    for field_name, field_type, typelist in fields:
        attrs = f'name="{field_name}" type="{field_type}"'
        if typelist:
            attrs += f' typelist="{typelist}"'
        rows.append(f"  <column {attrs}/>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<entityExtension name="{name}">\n' + "\n".join(rows) + "\n</entityExtension>\n"
    )


def typelist_xml(name: str, codes: list[str], *, extension: bool = False) -> str:
    root = "typelistExtension" if extension else "typelist"
    rows = [f'  <code name="{code}"/>' for code in codes]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<{root} name="{name}">\n' + "\n".join(rows) + f"\n</{root}>\n"
    )


def pcf_xml(name: str, widgets: list[tuple[str, str, str]]) -> str:
    rows = [
        f'    <{widget_type} id="{widget_id}" value="{binding}" label="{binding}"/>'
        for widget_type, widget_id, binding in widgets
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<PCF name="{name}">\n  <Screen name="{name}">\n'
        + "\n".join(rows)
        + "\n  </Screen>\n</PCF>\n"
    )


def template_xml(name: str, types: list[tuple[str, list[tuple[str, str]]]]) -> str:
    chunks = []
    for type_name, fields in types:
        rows = [f'    <field name="{f}" type="{t}"/>' for f, t in fields]
        chunks.append(f'  <type name="{type_name}">\n' + "\n".join(rows) + "\n  </type>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<productTemplate name="{name}">\n' + "\n".join(chunks) + "\n</productTemplate>\n"
    )


def product_xml(name: str, types: list[str], *, sbt: bool = False) -> str:
    attr = ' standardsBasedTemplate="true"' if sbt else ""
    rows = [f'  <type name="{type_name}"/>' for type_name in types]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<productModel name="{name}"{attr}>\n' + "\n".join(rows) + "\n</productModel>\n"
    )


COMMON_FILES: dict[str, str] = {
    "README.md": (
        "# Acme Personal Auto - Synthetic Legacy Estate\n\n"
        "Synthetic demonstration estate for PreFlight. No customer data, no confidential\n"
        "Guidewire content. Review context: pre-Retrofit snapshot, Qusar 2026.08.\n"
        "Cloud Retrofit without APD App. All dates and names are invented.\n"
    ),
    "config/metadata/entity/PersonalVehicle.eti": entity_xml(
        "PersonalVehicle",
        [
            ("ModelYear", "Integer", None),
            ("Make", "Text", None),
            ("VIN", "Text", None),
            ("Usage", "TypeKey", "VehicleUsage"),
            ("VehicleType", "TypeKey", "VehicleType"),
        ],
    ),
    "config/extensions/entity/PersonalVehicle.etx": entity_ext_xml(
        "PersonalVehicle",
        [("GarageLocation_Ext", "Text", None), ("Territory_Ext", "Integer", None)],
    ),
    "config/metadata/entity/VehicleDriver.eti": entity_xml(
        "VehicleDriver",
        [
            ("FirstName", "Text", None),
            ("LastName", "Text", None),
            ("LicenseNumber", "Text", None),
            ("DateOfBirth", "Date", None),
            ("ViolationType", "TypeKey", "ViolationType"),
        ],
    ),
    "config/extensions/entity/VehicleDriver.etx": entity_ext_xml(
        "VehicleDriver", [("CDL_Ext", "Boolean", None)]
    ),
    "config/metadata/entity/PersonalAutoLine.eti": entity_xml(
        "PersonalAutoLine",
        [("ProductCode", "Text", None), ("Edition", "Text", None)],
    ),
    "config/metadata/entity/PolicyPeriod.eti": entity_xml(
        "PolicyPeriod", [("PeriodStart", "Date", None), ("PeriodEnd", "Date", None)]
    ),
    "config/metadata/entity/PACoverage.eti": entity_xml(
        "PACoverage",
        [("CoverageType", "TypeKey", "CoverageType"), ("Limit", "TypeKey", "LimitType")],
    ),
    "config/metadata/entity/PACoverageTerm.eti": entity_xml(
        "PACoverageTerm", [("TermType", "Text", None), ("TermValue", "Integer", None)]
    ),
    "config/metadata/entity/DriverEligibility.eti": entity_xml(
        "DriverEligibility",
        [("Eligible", "Boolean", None), ("Reason", "TypeKey", "EligibilityReason")],
    ),
    "config/metadata/entity/RatingFactor.eti": entity_xml(
        "RatingFactor",
        [("FactorType", "TypeKey", "FactorType"), ("FactorValue", "Decimal", None)],
    ),
    "config/metadata/typelist/VehicleType.tti": typelist_xml("VehicleType", ["Passenger", "Trailer"]),
    "config/extensions/typelist/VehicleType.ttx": typelist_xml(
        "VehicleType", ["Motorcycle_Ext"], extension=True
    ),
    "config/metadata/typelist/VehicleUsage.tti": typelist_xml(
        "VehicleUsage", ["Pleasure", "Commute", "Business"]
    ),
    "config/metadata/typelist/ViolationType.tti": typelist_xml(
        "ViolationType", ["Speeding", "DUI"]
    ),
    "config/metadata/typelist/CoverageType.tti": typelist_xml(
        "CoverageType", ["Liability", "Collision", "Comprehensive"]
    ),
    "config/metadata/typelist/LimitType.tti": typelist_xml(
        "LimitType", ["PerPerson", "PerAccident"]
    ),
    "config/metadata/typelist/EligibilityReason.tti": typelist_xml(
        "EligibilityReason", ["Clean", "Suspended"]
    ),
    "config/metadata/typelist/FactorType.tti": typelist_xml(
        "FactorType", ["Age", "Territory", "Vehicle"]
    ),
    "config/web/pcf/policy/PAVehicleDV.pcf": pcf_xml(
        "PAVehicleDV",
        [
            ("TypeKeyInput", "VehicleType", "VehicleType"),
            ("TextInput", "ModelYear", "ModelYear"),
            ("TextInput", "GarageLocation_Ext", "GarageLocation_Ext"),
        ],
    ),
    "config/web/pcf/policy/PADriverDV.pcf": pcf_xml(
        "PADriverDV",
        [
            ("TextInput", "FirstName", "FirstName"),
            ("TextInput", "LastName", "LastName"),
            ("TypeKeyInput", "ViolationType", "ViolationType"),
        ],
    ),
    "config/web/pcf/policy/PACoverageDV.pcf": pcf_xml(
        "PACoverageDV",
        [
            ("TypeKeyInput", "CoverageType", "CoverageType"),
            ("TypeKeyInput", "Limit", "Limit"),
        ],
    ),
    "config/web/pcf/policy/PACoverageTermsDV.pcf": pcf_xml(
        "PACoverageTermsDV",
        [
            ("TypeKeyInput", "TermType", "TermType"),
            ("TextInput", "TermValue", "TermValue"),
        ],
    ),
    "config/web/pcf/policy/PAVehicleRatingDV.pcf": pcf_xml(
        "PAVehicleRatingDV",
        [
            ("TypeKeyInput", "FactorType", "FactorType"),
            ("TextInput", "FactorValue", "FactorValue"),
        ],
    ),
    "config/web/pcf/policy/PADriverEligibilityDV.pcf": pcf_xml(
        "PADriverEligibilityDV",
        [
            ("CheckBox", "Eligible", "Eligible"),
            ("TypeKeyInput", "Reason", "Reason"),
        ],
    ),
    "config/web/pcf/policy/PAPolicyQuestionsDV.pcf": pcf_xml(
        "PAPolicyQuestionsDV",
        [
            ("CheckBox", "GarageKept", "GarageKept"),
            ("TypeKeyInput", "Usage", "Usage"),
        ],
    ),
    "config/web/pcf/policy/legacy/PAVehicleDV.pcf": pcf_xml(
        "PAVehicleDV",
        [
            ("TypeKeyInput", "VehicleType", "VehicleType"),
            ("TextInput", "ModelYear", "ModelYear"),
        ],
    ),
    "config/resources/productmodel/PersonalAuto.xml": product_xml(
        "PersonalAuto",
        ["PAVehicle", "PADriver", "PALine", "PACoverage", "PersonalAutoRatingFactorConfiguration"],
    ),
    "product/template/PersonalAutoTemplate.xml": template_xml(
        "PersonalAuto",
        [
            ("PAVehicle", [("Year", "Integer"), ("VehicleType", "TypeKey"), ("GarageLocation", "Text"), ("Make", "Text"), ("VIN", "Text"), ("Usage", "TypeKey")]),
            ("PADriver", [("FirstName", "Text"), ("LastName", "Text"), ("LicenseNumber", "Text")]),
            ("PALine", [("ProductCode", "Text"), ("Edition", "Text")]),
            ("PACoverage", [("CoverageType", "TypeKey"), ("Limit", "TypeKey")]),
            ("PACoverageTerm", [("TermType", "Text"), ("TermValue", "Integer")]),
            ("DriverEligibility", [("Eligible", "Boolean"), ("Reason", "TypeKey")]),
            ("PAVehicleRatingFactor", [("FactorType", "TypeKey"), ("FactorValue", "Decimal")]),
        ],
    ),
    "product/template/ShortTypes.xml": template_xml(
        "ShortTypes",
        [
            ("PAVehicle", [("Year", "Integer"), ("VehicleType", "TypeKey")]),
            ("PADriver", [("FirstName", "Text")]),
        ],
    ),
    "config/apd/model/generate/json/template_gen_config.xml": (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<templateGenConfig product="pa">\n'
        "  <template file=\"product/template/PersonalAutoTemplate.xml\"/>\n"
        "  <setting name=\"applyToInstalledProduct\" value=\"true\"/>\n"
        "</templateGenConfig>\n"
    ),
    "gsrc/acme/validation/PersonalVehicleValidation.gs": (
        "package acme.validation\n\n"
        "uses gw.api.database.Query\n\n"
        "class PersonalVehicleValidation {\n"
        "  // Query.make(PersonalVehicle) in prose must not be treated as SQL.\n"
        "  function validate(vehicle : PersonalVehicle) : String {\n"
        '    var note = "java.sql.Connection in a string is prose"\n'
        "    if (vehicle.ModelYear < 1900) {\n"
        '      return "Invalid model year"\n'
        "    }\n"
        "    return null\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/rating/PersonalVehicleRating.gs": (
        "package acme.rating\n\n"
        "class PersonalVehicleRating {\n"
        "  function factor(vehicle : PersonalVehicle) : int {\n"
        "    return vehicle.ModelYear >= 2010 ? 100 : 120\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/query/PersonalVehicleQuery.gs": (
        "package acme.query\n\n"
        "uses java.sql.Connection\n"
        "uses java.sql.DriverManager\n\n"
        "class PersonalVehicleQuery {\n"
        "  function load() : Connection {\n"
        '    var conn = DriverManager.getConnection("jdbc:acme:vehicles")\n'
        '    var stmt = conn.createStatement()\n'
        '    stmt.executeQuery("SELECT * FROM pv_vehicle")\n'
        "    return conn\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/security/SecretConfig.gs": (
        "package acme.security\n\n"
        "class SecretConfig {\n"
        '  var apiKey = "sk-live-9f3a7c2b6d1e"\n'
        '  var password = "CHANGEME"\n'
        "}\n"
    ),
    "gsrc/acme/integration/LegacyVehicleServlet.gs": (
        "package acme.integration\n\n"
        "uses javax.servlet.http.HttpServlet\n"
        "uses javax.servlet.http.HttpServletRequest\n"
        "uses javax.servlet.http.HttpServletResponse\n\n"
        "class LegacyVehicleServlet extends HttpServlet {\n"
        "  override function doGet(req : HttpServletRequest, resp : HttpServletResponse) {\n"
        '    resp.getWriter().write("vehicles")\n'
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/transaction/BundleCommit.gs": (
        "package acme.transaction\n\n"
        "class BundleCommit {\n"
        "  function save(vehicle : PersonalVehicle) {\n"
        "    gw.transaction.Transaction.runWithNewBundle(\\bundle -> {\n"
        "      bundle.add(vehicle)\n"
        "      bundle.commit()\n"
        "    })\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/error/SwallowError.gs": (
        "package acme.error\n\n"
        "class SwallowError {\n"
        "  function risky() {\n"
        "    try {\n"
        "      maybeFail()\n"
        "    } catch (e : Exception) {\n"
        "      // ignored on purpose\n"
        "    }\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/internal/HiddenPackage.gs": (
        "package acme.internal\n\n"
        "uses gw.internal.util.ClassLoaderUtil\n"
        "uses com.guidewire.cc.system.SystemUtil\n\n"
        "class HiddenPackage {\n"
        "  function boot() {\n"
        "    ClassLoaderUtil.reload()\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/logging/Logging.gs": (
        "package acme.logging\n\n"
        "class Logging {\n"
        "  function dump(vehicle : PersonalVehicle, e : Exception) {\n"
        '    print("vehicle " + vehicle.VIN)\n'
        '    System.out.println("model " + vehicle.ModelYear)\n'
        "    e.printStackTrace()\n"
        '    print("ssn=" + vehicle.Driver.SSN)\n'
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/negatives/SafePatterns.gs": (
        "package acme.negatives\n\n"
        "uses gw.api.database.Query\n\n"
        "class SafePatterns {\n"
        "  // DriverManager.getConnection in a comment is prose.\n"
        '  var note = "java.sql.Connection in a string is prose"\n'
        "  function useQuery() {\n"
        "    var q = Query.make(PersonalVehicle)\n"
        "    q.select()\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/negatives/Placeholders.gs": (
        "package acme.negatives\n\n"
        "class Placeholders {\n"
        '  var password = "CHANGEME"\n'
        '  var token = "<placeholder>"\n'
        "}\n"
    ),
    "gsrc/acme/negatives/NoCommit.gs": (
        "package acme.negatives\n\n"
        "class NoCommit {\n"
        "  function save(vehicle : PersonalVehicle) {\n"
        "    gw.transaction.Transaction.runWithNewBundle(\\bundle -> {\n"
        "      bundle.add(vehicle)\n"
        "    })\n"
        "  }\n"
        "}\n"
    ),
    "gsrc/acme/negatives/CatchWithLogging.gs": (
        "package acme.negatives\n\n"
        "class CatchAndRethrow {\n"
        "  function safe() {\n"
        "    try {\n"
        "      maybeFail()\n"
        "    } catch (e : Exception) {\n"
        "      throw new RuntimeException(\"vehicle lookup failed\", e)\n"
        "    }\n"
        "  }\n"
        "}\n"
    ),
    "gtest/acme/PersonalVehicleValidationTest.gs": (
        "package acme\n\n"
        "class PersonalVehicleValidationTest extends GUnitTestClassBase {\n"
        "  function testValidModelYear() {\n"
        "    var vehicle = new PersonalVehicle()\n"
        "    vehicle.ModelYear = 2020\n"
        "    assertTrue(vehicle.ModelYear == 2020)\n"
        "  }\n"
        "}\n"
    ),
    "gtest/acme/PersonalVehicleRatingDBTest.gs": (
        "package acme\n\n"
        "class PersonalVehicleRatingDBTest extends GUnitTestClassBase {\n"
        "  function testRatingRows() {\n"
        "    var q = Query.make(PersonalVehicle)\n"
        "    var rows = q.select().toList()\n"
        "    loadSampleData()\n"
        "    assertTrue(rows.size() >= 0)\n"
        "  }\n"
        "}\n"
    ),
    "gtest/acme/PersonalVehiclePureTest.gs": (
        "package acme\n\n"
        "class PersonalVehiclePureTest extends GUnitTestClassBase {\n"
        "  function testYearBoundary() {\n"
        "    assertTrue(1900 < 2020)\n"
        "  }\n"
        "}\n"
    ),
    "config/resources/productmodel/WorkersCompensation.xml": product_xml(
        "WorkersCompensation", ["WCLine", "WCEmployee"], sbt=True
    ),
    "config/web/pcf/wc/WCEmployeeDV.pcf": pcf_xml(
        "WCEmployeeDV", [("TextInput", "FirstName", "FirstName")]
    ),
    "config/metadata/entity/WCEmployee.eti": entity_xml(
        "WCEmployee", [("FirstName", "Text", None)]
    ),
    "data/vehicle_rating_inputs.csv": "factor,value\nage,1.2\nterritory,1.1\n",
    "docs/legacy-notes.txt": "Synthetic notes. Rating tables are not part of this snapshot.\n",
    "config/web/pcf/policy/BrokenScreen.pcf": "<PCF name=\"BrokenScreen\"><Screen>",
    "assets/dealer-logo.png": "\x89PNG\r\n\x1a\n\x00\x00synthetic",
    "assets/rate-table.xls": "\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00synthetic",
    "generated/gsrc/gw/generated/GeneratedBase.gs": (
        "// GENERATED - DO NOT EDIT\npackage gw.generated\nclass GeneratedBase {\n}\n"
    ),
    "plugins/acme_ext/plugin.xml": "<plugin name=\"acme_ext\"/>\n",
}


COMMON_FILES.update({
    "gsrc/acme/query/PersonalVehicleQueryB.gs": (
        "package acme.query\n\nuses java.sql.Statement\n\nclass PersonalVehicleQueryB {\n"
        "  function load(stmt : Statement) {\n"
        "    stmt.executeQuery(\"SELECT VIN FROM pv_vehicle\")\n"
        "  }\n}\n"
    ),
    "gsrc/acme/query/PersonalVehicleQueryC.gs": (
        "package acme.query\n\nuses java.sql.DriverManager\n\nclass PersonalVehicleQueryC {\n"
        "  function load() {\n"
        "    DriverManager.getConnection(\"jdbc:acme:vehicles\")\n"
        "  }\n}\n"
    ),
    "gsrc/acme/security/SecretConfigB.gs": (
        "package acme.security\n\nclass SecretConfigB {\n"
        "  var token = \"tok-live-4b8c1d\"\n}\n"
    ),
    "gsrc/acme/security/SecretConfigC.gs": (
        "package acme.security\n\nclass SecretConfigC {\n"
        "  var secret : String = \"s3cr3t-live-value\"\n}\n"
    ),
    "gsrc/acme/internal/HiddenPackageB.gs": (
        "package acme.internal\n\nuses gw.internal.util.ReflectionUtil\n\nclass HiddenPackageB {\n"
        "  function boot() { ReflectionUtil.reload() }\n}\n"
    ),
    "gsrc/acme/internal/HiddenPackageC.gs": (
        "package acme.internal\n\nuses com.guidewire.cc.system.SystemUtil\n\nclass HiddenPackageC {\n"
        "  function boot() { SystemUtil.ping() }\n}\n"
    ),
    "gsrc/acme/error/SwallowErrorB.gs": (
        "package acme.error\n\nclass SwallowErrorB {\n  function risky() {\n"
        "    try { maybeFail() } catch (e : Exception) { }\n  }\n}\n"
    ),
    "gsrc/acme/error/SwallowErrorC.gs": (
        "package acme.error\n\nclass SwallowErrorC {\n  function risky() {\n"
        "    try { maybeFail() } catch (e : Exception) { ; }\n  }\n}\n"
    ),
    "gsrc/acme/transaction/BundleCommitB.gs": (
        "package acme.transaction\n\nclass BundleCommitB {\n  function save(v : PersonalVehicle) {\n"
        "    gw.transaction.Transaction.runWithNewBundle(\\bundle -> {\n"
        "      bundle.add(v)\n      bundle.commit()\n    })\n  }\n}\n"
    ),
    "gsrc/acme/transaction/BundleCommitC.gs": (
        "package acme.transaction\n\nclass BundleCommitC {\n  function save(v : PersonalVehicle) {\n"
        "    gw.transaction.Transaction.runWithNewBundle(\\bundle -> { bundle.add(v); bundle.commit() })\n"
        "  }\n}\n"
    ),
    "gsrc/acme/integration/LegacyVehicleServletB.gs": (
        "package acme.integration\n\nuses javax.servlet.http.HttpServlet\n\n"
        "class LegacyVehicleServletB extends HttpServlet {\n  override function doGet() { }\n}\n"
    ),
    "gsrc/acme/integration/LegacyVehicleServletC.gs": (
        "package acme.integration\n\nimport javax.servlet.http.HttpServlet\n\n"
        "class LegacyVehicleServletC extends HttpServlet {\n  override function doPost() { }\n}\n"
    ),
    "product/template/LongTypeA.xml": template_xml("LongTypeA", [("PersonalAutoRatingFactorConfiguration", [("Factor", "Decimal")])]),
    "product/template/LongTypeB.xml": template_xml("LongTypeB", [("PersonalAutoUnderwritingConfiguration", [("Rule", "Text")])]),
    "product/template/LongTypeC.xml": template_xml("LongTypeC", [("PersonalAutoEligibilityConfiguration", [("Eligible", "Boolean")])]),
    "product/template/ShortTypesB.xml": template_xml("ShortTypesB", [("PAVehicle", [("Year", "Integer")])]),
    "product/template/ShortTypesC.xml": template_xml("ShortTypesC", [("PACoverage", [("Limit", "TypeKey")])]),
    "gtest/acme/PersonalVehicleRatingDBTestB.gs": (
        "package acme\nclass PersonalVehicleRatingDBTestB extends GUnitTestClassBase {\n"
        "  function testRows() { var q = Query.make(PersonalVehicle); q.select(); loadSampleData() }\n}\n"
    ),
    "gtest/acme/PersonalVehicleRatingDBTestC.gs": (
        "package acme\nclass PersonalVehicleRatingDBTestC extends GUnitTestClassBase {\n"
        "  function testRows() { DriverManager.getConnection(\"jdbc:acme\") }\n}\n"
    ),
    "gsrc/acme/negatives/SearchClient.gs": (
        "package acme.negatives\nclass SearchClient {\n"
        "  function run() { client.executeQuery(\"search\") }\n}\n"
    ),
    "gsrc/acme/negatives/EnvSecret.gs": (
        "package acme.negatives\nclass EnvSecret {\n"
        "  var apiKey = System.getenv(\"API_KEY\")\n}\n"
    ),
    "gsrc/acme/negatives/PublicApi.gs": (
        "package acme.negatives\nuses com.guidewire.public.api.Thing\nuses gw.api.database.Query\n"
        "class PublicApi { function run() { Query.make(PersonalVehicle) } }\n"
    ),
    "gsrc/acme/negatives/PackageComment.gs": (
        "package acme.negatives\n// gw.internal.util in a comment is prose\nclass PackageComment { }\n"
    ),
    "gtest/acme/PersonalVehiclePureTestB.gs": (
        "package acme\nclass PersonalVehiclePureTestB extends GUnitTestClassBase {\n"
        "  function testMath() { assertTrue(2 + 2 == 4) }\n}\n"
    ),
    "gsrc/acme/negatives/CommitComment.gs": (
        "package acme.negatives\nclass CommitComment {\n"
        "  // bundle.commit() in a comment is prose\n}\n"
    ),
    "gsrc/acme/negatives/ServletProse.gs": (
        "package acme.negatives\n// class X extends HttpServlet is prose\nclass ServletProse { }\n"
    ),
})


NORTHSTAR_FILES: dict[str, str] = {
    "README.md": (
        "# Northstar Auto - Synthetic Holdout Estate\n\n"
        "Synthetic holdout with different file and type naming. No customer data.\n"
    ),
    "config/metadata/entity/AutoVehicle.eti": entity_xml(
        "AutoVehicle",
        [
            ("ModelYear", "Integer", None),
            ("Make", "Text", None),
            ("VIN", "Text", None),
            ("Usage", "TypeKey", "AutoUsage"),
            ("VehicleType", "TypeKey", "AutoKind"),
        ],
    ),
    "config/extensions/entity/AutoVehicle.etx": entity_ext_xml(
        "AutoVehicle", [("GarageLocation_Ext", "Text", None), ("Territory_Ext", "Integer", None)]
    ),
    "config/metadata/entity/AutoDriver.eti": entity_xml(
        "AutoDriver",
        [("FirstName", "Text", None), ("LastName", "Text", None), ("LicenseNumber", "Text", None)],
    ),
    "config/metadata/entity/AutoCoverage.eti": entity_xml(
        "AutoCoverage", [("CoverageType", "TypeKey", "AutoCoverageType"), ("Limit", "Integer", None)]
    ),
    "config/metadata/typelist/AutoKind.tti": typelist_xml("AutoKind", ["Passenger", "Trailer"]),
    "config/extensions/typelist/AutoKind.ttx": typelist_xml(
        "AutoKind", ["Motorcycle_Ext"], extension=True
    ),
    "config/metadata/typelist/AutoUsage.tti": typelist_xml("AutoUsage", ["Pleasure", "Commute"]),
    "config/metadata/typelist/AutoCoverageType.tti": typelist_xml(
        "AutoCoverageType", ["Liability", "Collision"]
    ),
    "config/web/pcf/auto/AutoVehicleDV.pcf": pcf_xml(
        "AutoVehicleDV",
        [
            ("TypeKeyInput", "VehicleType", "VehicleType"),
            ("TextInput", "ModelYear", "ModelYear"),
            ("TextInput", "GarageLocation_Ext", "GarageLocation_Ext"),
        ],
    ),
    "config/web/pcf/auto/AutoDriverDV.pcf": pcf_xml(
        "AutoDriverDV",
        [("TextInput", "FirstName", "FirstName"), ("TextInput", "LastName", "LastName")],
    ),
    "config/web/pcf/auto/AutoCoverageDV.pcf": pcf_xml(
        "AutoCoverageDV", [("TypeKeyInput", "CoverageType", "CoverageType")]
    ),
    "config/web/pcf/auto/AutoPolicyQuestionsDV.pcf": pcf_xml(
        "AutoPolicyQuestionsDV", [("CheckBox", "GarageKept", "GarageKept")]
    ),
    "config/resources/productmodel/AutoProduct.xml": product_xml(
        "AutoProduct", ["AutoVehicle", "AutoDriver", "AutoCoverage"]
    ),
    "product/template/AutoTemplate.xml": template_xml(
        "AutoProduct",
        [
            ("AutoVehicle", [("Year", "Integer"), ("VehicleType", "TypeKey"), ("GarageLocation", "Text")]),
            ("AutoDriver", [("FirstName", "Text"), ("LastName", "Text")]),
            ("AutoCoverage", [("CoverageType", "TypeKey")]),
        ],
    ),
    "gsrc/ns/validation/AutoVehicleValidation.gs": (
        "package ns.validation\nclass AutoVehicleValidation {\n"
        "  function validate(v : AutoVehicle) : String { return null }\n"
        "}\n"
    ),
    "gtest/ns/AutoVehicleValidationTest.gs": (
        "package ns\nclass AutoVehicleValidationTest extends GUnitTestClassBase {\n"
        "  function testYear() { assertTrue(2020 > 1900) }\n"
        "}\n"
    ),
    "config/web/pcf/auto/BrokenScreen.pcf": "<PCF name=\"BrokenScreen\">",
    "assets/logo.png": "\x89PNG\r\n\x1a\n\x00\x00synthetic",
}


def pad_files(root: Path, target: int) -> None:
    current = sum(1 for p in root.rglob("*") if p.is_file())
    if current > target:
        raise RuntimeError(f"{root} already has {current} files, target is {target}")
    index = 0
    while current < target:
        bucket = index % 6
        if bucket == 0:
            rel = f"generated/gsrc/gw/generated/GeneratedType{index}.gs"
            text = (
                "// GENERATED - DO NOT EDIT\n"
                f"package gw.generated\nclass GeneratedType{index} {{\n"
                f"  function value() : int {{ return {index} }}\n}}\n"
            )
        elif bucket == 1:
            rel = f"generated/pcf/GeneratedScreen{index}.pcf"
            text = pcf_xml(f"GeneratedScreen{index}", [("TextInput", f"Field{index}", f"Field{index}")])
        elif bucket == 2:
            rel = f"config/metadata/entity/GeneratedEntity{index}.eti"
            text = entity_xml(f"GeneratedEntity{index}", [(f"Field{index}", "Text", None)])
        elif bucket == 3:
            rel = f"config/metadata/typelist/GeneratedList{index}.tti"
            text = typelist_xml(f"GeneratedList{index}", [f"Value{index}"])
        elif bucket == 4:
            rel = f"config/resources/generated/GeneratedConfig{index}.xml"
            text = f'<?xml version="1.0"?>\n<config name="GeneratedConfig{index}"/>\n'
        else:
            rel = f"docs/generated/Note{index}.md"
            text = f"# Generated note {index}\nSynthetic documentation noise.\n"
        write(root / rel, text)
        current += 1
        index += 1


def build(root: Path, files: dict[str, str], target: int) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for rel, text in files.items():
        path = root / rel
        if rel.endswith((".png", ".xls")):
            write_bytes(path, text.encode("latin-1"))
        else:
            write(path, text)
    pad_files(root, target)


def truth_features() -> dict:
    return {
        "schema_version": "1.0",
        "fixture": "acme-pc-2026.10",
        "features": [
            {"feature_id": "PA-VEH-01", "capability": "vehicle_information", "name": "Vehicle Information", "lob": "PersonalAuto", "anchors": ["config/web/pcf/policy/PAVehicleDV.pcf", "config/metadata/entity/PersonalVehicle.eti"]},
            {"feature_id": "PA-DRV-01", "capability": "driver_information", "name": "Driver Information", "lob": "PersonalAuto", "anchors": ["config/web/pcf/policy/PADriverDV.pcf", "config/metadata/entity/VehicleDriver.eti"]},
            {"feature_id": "PA-COV-01", "capability": "coverage_selection", "name": "Coverage Selection", "lob": "PersonalAuto", "anchors": ["config/web/pcf/policy/PACoverageDV.pcf", "config/metadata/entity/PACoverage.eti"]},
            {"feature_id": "PA-COV-02", "capability": "coverage_terms", "name": "Coverage Terms", "lob": "PersonalAuto", "anchors": ["config/web/pcf/policy/PACoverageTermsDV.pcf", "config/metadata/entity/PACoverageTerm.eti"]},
            {"feature_id": "PA-VEH-02", "capability": "vehicle_rating", "name": "Vehicle Rating Factors", "lob": "PersonalAuto", "anchors": ["config/web/pcf/policy/PAVehicleRatingDV.pcf", "config/metadata/entity/RatingFactor.eti"]},
            {"feature_id": "PA-DRV-02", "capability": "driver_eligibility", "name": "Driver Eligibility", "lob": "PersonalAuto", "anchors": ["config/web/pcf/policy/PADriverEligibilityDV.pcf", "config/metadata/entity/DriverEligibility.eti"]},
            {"feature_id": "PA-POL-01", "capability": "policy_line", "name": "Policy Line and Editions", "lob": "PersonalAuto", "anchors": ["config/metadata/entity/PersonalAutoLine.eti", "product/template/PersonalAutoTemplate.xml"]},
            {"feature_id": "PA-POL-02", "capability": "policy_questions", "name": "Policy Questions", "lob": "PersonalAuto", "anchors": ["config/web/pcf/policy/PAPolicyQuestionsDV.pcf"]},
        ],
    }


def truth_holdout() -> dict:
    return {
        "schema_version": "1.0",
        "fixture": "northstar-pc-2026.10",
        "features": [
            {"feature_id": "PA-VEH-01", "capability": "vehicle_information", "name": "Vehicle Information", "lob": "PersonalAuto", "anchors": ["config/web/pcf/auto/AutoVehicleDV.pcf", "config/metadata/entity/AutoVehicle.eti"]},
            {"feature_id": "PA-DRV-01", "capability": "driver_information", "name": "Driver Information", "lob": "PersonalAuto", "anchors": ["config/web/pcf/auto/AutoDriverDV.pcf", "config/metadata/entity/AutoDriver.eti"]},
            {"feature_id": "PA-COV-01", "capability": "coverage_selection", "name": "Coverage Selection", "lob": "PersonalAuto", "anchors": ["config/web/pcf/auto/AutoCoverageDV.pcf", "config/metadata/entity/AutoCoverage.eti"]},
            {"feature_id": "PA-POL-02", "capability": "policy_questions", "name": "Policy Questions", "lob": "PersonalAuto", "anchors": ["config/web/pcf/auto/AutoPolicyQuestionsDV.pcf"]},
        ],
        "holdout": True,
        "note": "Naming-shift holdout. Never imported into the demo or used to author rules.",
    }


def truth_findings() -> dict:
    return {
        "schema_version": "1.0",
        "fixture": "acme-pc-2026.10",
        "rules": {
            "PF-GW-SQL-001": {
                "positives": [
                    "gsrc/acme/query/PersonalVehicleQuery.gs",
                    "gsrc/acme/query/PersonalVehicleQueryB.gs",
                    "gsrc/acme/query/PersonalVehicleQueryC.gs",
                ],
                "negatives": [
                    "gsrc/acme/negatives/SafePatterns.gs",
                    "gsrc/acme/validation/PersonalVehicleValidation.gs",
                    "gsrc/acme/negatives/SearchClient.gs",
                ],
            },
            "PF-GW-SEC-001": {
                "positives": [
                    "gsrc/acme/security/SecretConfig.gs",
                    "gsrc/acme/security/SecretConfigB.gs",
                    "gsrc/acme/security/SecretConfigC.gs",
                ],
                "negatives": [
                    "gsrc/acme/negatives/Placeholders.gs",
                    "gsrc/acme/negatives/EnvSecret.gs",
                    "gsrc/acme/negatives/PublicApi.gs",
                ],
            },
            "PF-GW-PKG-001": {
                "positives": [
                    "gsrc/acme/internal/HiddenPackage.gs",
                    "gsrc/acme/internal/HiddenPackageB.gs",
                    "gsrc/acme/internal/HiddenPackageC.gs",
                ],
                "negatives": [
                    "gsrc/acme/negatives/SafePatterns.gs",
                    "gsrc/acme/negatives/PublicApi.gs",
                    "gsrc/acme/negatives/PackageComment.gs",
                ],
            },
            "PF-GW-EXC-001": {
                "positives": [
                    "gsrc/acme/error/SwallowError.gs",
                    "gsrc/acme/error/SwallowErrorB.gs",
                    "gsrc/acme/error/SwallowErrorC.gs",
                ],
                "negatives": [
                    "gsrc/acme/negatives/CatchWithLogging.gs",
                    "gsrc/acme/negatives/PackageComment.gs",
                    "gsrc/acme/negatives/SafePatterns.gs",
                ],
            },
            "PF-GW-TX-001": {
                "positives": [
                    "gsrc/acme/transaction/BundleCommit.gs",
                    "gsrc/acme/transaction/BundleCommitB.gs",
                    "gsrc/acme/transaction/BundleCommitC.gs",
                ],
                "negatives": [
                    "gsrc/acme/negatives/NoCommit.gs",
                    "gsrc/acme/negatives/CommitComment.gs",
                    "gsrc/acme/negatives/SearchClient.gs",
                ],
            },
            "PF-GW-SRV-001": {
                "positives": [
                    "gsrc/acme/integration/LegacyVehicleServlet.gs",
                    "gsrc/acme/integration/LegacyVehicleServletB.gs",
                    "gsrc/acme/integration/LegacyVehicleServletC.gs",
                ],
                "negatives": [
                    "gsrc/acme/negatives/SafePatterns.gs",
                    "gsrc/acme/negatives/ServletProse.gs",
                    "gsrc/acme/negatives/PublicApi.gs",
                ],
            },
            "PF-GW-NAM-001": {
                "positives": [
                    "product/template/LongTypeA.xml",
                    "product/template/LongTypeB.xml",
                    "product/template/LongTypeC.xml",
                ],
                "negatives": [
                    "product/template/ShortTypes.xml",
                    "product/template/ShortTypesB.xml",
                    "product/template/ShortTypesC.xml",
                ],
            },
            "PF-GW-GUNIT-001": {
                "positives": [
                    "gtest/acme/PersonalVehicleRatingDBTest.gs",
                    "gtest/acme/PersonalVehicleRatingDBTestB.gs",
                    "gtest/acme/PersonalVehicleRatingDBTestC.gs",
                ],
                "negatives": [
                    "gtest/acme/PersonalVehicleValidationTest.gs",
                    "gtest/acme/PersonalVehiclePureTest.gs",
                    "gtest/acme/PersonalVehiclePureTestB.gs",
                ],
            },
        },
        "thesis_rules": {
            "PF-GW-LOG-001": {"positives": ["gsrc/acme/logging/Logging.gs"], "negatives": ["gsrc/acme/negatives/SafePatterns.gs"]},
            "PF-GW-LOG-002": {"positives": ["gsrc/acme/logging/Logging.gs"], "negatives": ["gsrc/acme/negatives/CatchWithLogging.gs"]},
        },
    }


def truth_mappings() -> dict:
    rules = [
        ("R-CG-01", "PAVehicle", "apd_template", "codegen.PAVehicle.nameOverride", "PersonalVehicle", "mapped_transformed", "guidewire-doc"),
        ("R-CG-02", "PAVehicle.Year", "apd_template", "codegen.PAVehicle.fields.Year.nameOverride", "ModelYear", "mapped_transformed", "guidewire-doc"),
        ("R-CG-03", "PADriver", "apd_template", "codegen.PADriver.nameOverride", "VehicleDriver", "mapped_transformed", "guidewire-doc"),
        ("R-CG-04", "PALine", "apd_template", "codegen.PALine.nameOverride", "PersonalAutoLine", "mapped_transformed", "guidewire-doc"),
        ("R-GW-24-01", "PersonalAutoRatingFactorConfiguration", "apd_template", "codegen.PersonalAutoRatingFactor.nameOverride", "PersonalAutoRatingFactorConfiguration", "mapped_transformed", "guidewire-doc"),
        ("R-API-01", "PersonalVehicle.VehicleType", "installed_entity", "schema.vehicleType", "vehicleType", "mapped_exact", "preflight-convention"),
        ("R-API-02", "PersonalVehicle.GarageLocation_Ext", "installed_entity", "schema.garageLocation", "garageLocation", "mapped_transformed", "preflight-convention"),
        ("R-API-03", "PersonalVehicle.ModelYear", "installed_entity", "schema.modelYear", "modelYear", "mapped_transformed", "preflight-convention"),
        ("R-API-04", "PersonalVehicle.Make", "installed_entity", "schema.make", "make", "mapped_exact", "preflight-convention"),
        ("R-API-05", "PersonalVehicle.VIN", "installed_entity", "schema.vin", "vin", "mapped_exact", "preflight-convention"),
        ("R-API-06", "PersonalVehicle.Usage", "installed_entity", "schema.usage", "usage", "mapped_exact", "preflight-convention"),
        ("R-TYP-01", "VehicleType.Motorcycle_Ext", "typelist", "schema.vehicleType.motorcycle", "motorcycle", "mapped_transformed", "preflight-convention"),
    ]
    return {
        "schema_version": "1.0",
        "fixture": "acme-pc-2026.10",
        "mappings": [
            {
                "mapping_id": f"GM-{i+1:02d}", "rule_id": r[0], "source_ref": r[1],
                "source_layer": r[2], "target_path": r[3], "target_name": r[4],
                "disposition": r[5], "provenance": r[6],
            }
            for i, r in enumerate(rules)
        ],
    }


def truth_gaps() -> dict:
    return {
        "schema_version": "1.0",
        "fixture": "acme-pc-2026.10",
        "gaps": [
            {"gap_id": "G-01", "kind": "missing_source", "subject": "territory", "impact": "high", "anchor": "config/extensions/entity/PersonalVehicle.etx"},
            {"gap_id": "G-02", "kind": "unsupported", "subject": "rating inputs", "impact": "medium", "anchor": "data/vehicle_rating_inputs.csv"},
            {"gap_id": "G-03", "kind": "ambiguous_reference", "subject": "duplicate PAVehicleDV screen", "impact": "medium", "anchor": "config/web/pcf/policy/legacy/PAVehicleDV.pcf"},
        ],
    }


def truth_reference_target() -> dict:
    return {
        "schema_version": "1.0",
        "feature_id": "PA-VEH-01",
        "author": "Internally authored reference pass (AI-assisted; not independent)",
        "authored_blind": False,
        "independence": "Internally authored by the same build team, AI-assisted; not independent. Reported as a limitation.",
        "target_scope_complete": True,
        "properties": [
            {"source": "PersonalVehicle.ModelYear", "target": "modelYear", "class": "changed", "rule_id": "R-API-03"},
            {"source": "PersonalVehicle.Make", "target": "make", "class": "preserved", "rule_id": "R-API-04"},
            {"source": "PersonalVehicle.VIN", "target": "vin", "class": "preserved", "rule_id": "R-API-05"},
            {"source": "PersonalVehicle.Usage", "target": "usage", "class": "preserved", "rule_id": "R-API-06"},
            {"source": "PersonalVehicle.VehicleType", "target": "vehicleType", "class": "preserved", "rule_id": "R-API-01"},
            {"source": "PersonalVehicle.GarageLocation_Ext", "target": "garageLocation", "class": "changed", "rule_id": "R-API-02"},
            {"source": "VehicleType.Motorcycle_Ext", "target": "vehicleType.motorcycle", "class": "changed", "rule_id": "R-TYP-01"},
            {"source": "PersonalVehicle.Territory_Ext", "target": None, "class": "unresolved", "scope_complete": False, "rule_id": "R-UNR-01"},
        ],
    }


def main() -> None:
    build(FIXTURES / "acme-pc-2026.10", COMMON_FILES, MAIN_FILES)
    build(FIXTURES / "demo-slice-300", COMMON_FILES, DEMO_FILES)
    build(FIXTURES / "northstar-pc-2026.10", NORTHSTAR_FILES, HOLDOUT_FILES)

    GROUND.mkdir(exist_ok=True)
    (GROUND / "features.json").write_text(json.dumps(truth_features(), indent=2) + "\n", encoding="utf-8")
    (GROUND / "holdout_features.json").write_text(json.dumps(truth_holdout(), indent=2) + "\n", encoding="utf-8")
    (GROUND / "findings.json").write_text(json.dumps(truth_findings(), indent=2) + "\n", encoding="utf-8")
    (GROUND / "mappings.json").write_text(json.dumps(truth_mappings(), indent=2) + "\n", encoding="utf-8")
    (GROUND / "gaps.json").write_text(json.dumps(truth_gaps(), indent=2) + "\n", encoding="utf-8")
    reference = GROUND / "reference_target"
    reference.mkdir(exist_ok=True)
    (reference / "pa_veh_01_reference.json").write_text(
        json.dumps(truth_reference_target(), indent=2) + "\n", encoding="utf-8"
    )

    for name in ["acme-pc-2026.10", "demo-slice-300", "northstar-pc-2026.10"]:
        count = sum(1 for p in (FIXTURES / name).rglob("*") if p.is_file())
        print(f"{name}: {count} files")


if __name__ == "__main__":
    main()
