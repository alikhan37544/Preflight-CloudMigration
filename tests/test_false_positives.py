"""Explicit false-positive gate for the review rules.

Each case is a deliberate near-miss that a naive regex would flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.discovery import DiscoveryResult
from app.services.intake import build_manifest
from app.services.pipeline import execute_run
from app.services.review import run_review
from app.store import RunStore


def review_files(tmp_path: Path, files: dict[str, str]):
    root = tmp_path / "snapshot"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    manifest = build_manifest(root, snapshot_id="S-FP", project_id="FP")
    return run_review(root, manifest, DiscoveryResult(), include_thesis=True)


def paths_for(review, rule_id: str) -> set[str]:
    evidence = {e.evidence_id: e for e in review.evidence}
    return {
        evidence[eid].path
        for finding in review.findings
        if finding.rule_id == rule_id
        for eid in finding.evidence_ids
        if eid in evidence
    }


def test_sql_in_comment_and_string_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/SqlProse.gs": '''package acme
// DriverManager.getConnection("jdbc:acme") in prose
class SqlProse {
  var note = "java.sql.Connection and createStatement() in a string"
}
''',
    })
    assert paths_for(review, "PF-GW-SQL-001") == set()


def test_supported_database_api_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/SupportedQuery.gs": '''package acme
uses gw.api.database.Query
uses gw.pl.persistence.core.Bundle
class SupportedQuery {
  function rows() {
    return Query.make(PersonalVehicle).select().toList()
  }
}
''',
    })
    assert paths_for(review, "PF-GW-SQL-001") == set()
    assert paths_for(review, "PF-GW-PKG-001") == set()


def test_placeholders_and_env_references_are_not_secrets(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/Placeholders.gs": '''package acme
class Placeholders {
  var password = "CHANGEME"
  var token = "<placeholder>"
  var apiKey = "${API_KEY}"
}
''',
    })
    assert paths_for(review, "PF-GW-SEC-001") == set()


def test_secret_in_a_comment_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/SecretComment.gs": '''package acme
class SecretComment {
  // password = "hunter2" in a comment is prose
  var note = "not an assignment"
}
''',
    })
    assert paths_for(review, "PF-GW-SEC-001") == set()


def test_real_secret_is_still_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/RealSecret.gs": '''package acme
class RealSecret {
  var apiKey = "sk-live-example-value"
}
''',
    })
    assert "gsrc/acme/RealSecret.gs" in paths_for(review, "PF-GW-SEC-001")


def test_servlet_in_comment_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/ServletProse.gs": '''package acme
// class Legacy extends HttpServlet is prose
class ServletProse {
}
''',
    })
    assert paths_for(review, "PF-GW-SRV-001") == set()


def test_commit_outside_run_with_new_bundle_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/PlainCommit.gs": '''package acme
class PlainCommit {
  function save(bundle : Bundle) {
    bundle.commit()
  }
}
''',
    })
    assert paths_for(review, "PF-GW-TX-001") == set()


def test_catch_with_context_rethrow_is_not_swallowed(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/CatchRethrow.gs": '''package acme
class CatchRethrow {
  function run() {
    try { risky() } catch (e : Exception) {
      throw new RuntimeException("vehicle lookup failed", e)
    }
  }
}
''',
    })
    assert paths_for(review, "PF-GW-EXC-001") == set()


def test_pure_unit_test_is_not_db_coupled(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gtest/acme/PureTest.gs": '''package acme
class PureTest extends GUnitTestClassBase {
  function testMath() { assertTrue(1 + 1 == 2) }
}
''',
    })
    assert paths_for(review, "PF-GW-GUNIT-001") == set()


def test_sbt_false_marker_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "config/resources/productmodel/NotSbt.xml": '<?xml version="1.0"?>\n<productModel name="X" standardsBasedTemplate="false"/>\n',
    })
    assert review.readiness == []


def test_type_name_at_24_characters_is_not_flagged(tmp_path: Path) -> None:
    name = "A" * 24
    review = review_files(tmp_path, {
        "product/template/Template.xml": f'<?xml version="1.0"?>\n<productTemplate name="X"><type name="{name}"/></productTemplate>\n',
    })
    assert paths_for(review, "PF-GW-NAM-001") == set()


def test_print_in_comment_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/PrintProse.gs": '''package acme
// System.out.println and printStackTrace are prose here
class PrintProse {
}
''',
    })
    assert paths_for(review, "PF-GW-LOG-002") == set()


def test_typed_secret_declaration_is_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/TypedSecret.gs": 'package acme\nclass TypedSecret {\n  var password : String = "hunter2"\n}\n',
    })
    assert "gsrc/acme/TypedSecret.gs" in paths_for(review, "PF-GW-SEC-001")


def test_non_jdbc_execute_query_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/SearchClient.gs": 'package acme\nclass SearchClient {\n  function run() { client.executeQuery("search") }\n}\n',
    })
    assert paths_for(review, "PF-GW-SQL-001") == set()


def test_java_sql_resultset_is_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/ResultSetReader.gs": 'package acme\nuses java.sql.ResultSet\nclass ResultSetReader {\n  function read(rs : ResultSet) {}\n}\n',
    })
    assert "gsrc/acme/ResultSetReader.gs" in paths_for(review, "PF-GW-SQL-001")


def test_public_guidewire_namespace_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/PublicApi.gs": '''package acme
uses com.guidewire.public.api.Thing
uses gw.api.database.Query
class PublicApi {
  function run() { Query.make(PersonalVehicle) }
}
''',
    })
    assert paths_for(review, "PF-GW-PKG-001") == set()


def test_catch_with_only_semicolon_is_swallowed(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/CatchSemicolon.gs": '''package acme
class CatchSemicolon {
  function run() {
    try { risky() } catch (e : Exception) { ; }
  }
}
''',
    })
    assert "gsrc/acme/CatchSemicolon.gs" in paths_for(review, "PF-GW-EXC-001")


def test_sbt_single_quotes_and_spacing_are_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "config/resources/productmodel/SbtSingle.xml": "<?xml version=\"1.0\"?>\n<productModel name=\"X\" standardsBasedTemplate='true'/>\n",
        "config/resources/productmodel/SbtSpaced.xml": "<?xml version=\"1.0\"?>\n<productModel name=\"Y\" standardsBasedTemplate = \"true\"/>\n",
    })
    assert len(review.readiness) == 2


def test_sbt_true_in_comment_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "config/resources/productmodel/SbtComment.xml": '<?xml version="1.0"?>\n<!-- standardsBasedTemplate="true" -->\n<productModel name="X" standardsBasedTemplate="false"/>\n',
    })
    assert review.readiness == []


def test_multiline_log_call_is_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/LogMultiline.gs": '''package acme
class LogMultiline {
  function run(v : PersonalVehicle) {
    log.error(
      "SSN " + v.SSN
    )
  }
}
''',
    })
    assert "gsrc/acme/LogMultiline.gs" in paths_for(review, "PF-GW-LOG-001")


def test_log_prose_is_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/LogProse.gs": 'package acme\n// Never log the VIN or SSN in prose\nclass LogProse {\n  var note = "Never log the VIN or SSN"\n}\n',
    })
    assert paths_for(review, "PF-GW-LOG-001") == set()


def test_websocket_get_connection_is_not_gunit_db(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gtest/adv/NetworkClientTest.gs": 'package adv\nclass NetworkClientTest extends GUnitTestClassBase {\n  function testSocket() { Client.getConnection("ws://example") }\n}\n',
    })
    assert paths_for(review, "PF-GW-GUNIT-001") == set()


def test_gtest_path_without_test_suffix_is_db_coupled(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gtest/adv/RatingChecks.gs": 'package adv\nclass RatingChecks extends GUnitTestClassBase {\n  function check() { Query.make(PersonalVehicle) }\n}\n',
    })
    assert "gtest/adv/RatingChecks.gs" in paths_for(review, "PF-GW-GUNIT-001")


def test_production_filename_ending_in_contest_is_not_a_test(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/adv/Contest.gs": 'package adv\nclass Contest {\n  function rows() { Query.make(PersonalVehicle) }\n}\n',
    })
    assert paths_for(review, "PF-GW-GUNIT-001") == set()


def test_root_level_template_path_is_scanned_for_long_names(tmp_path: Path) -> None:
    long_name = "A" * 25
    review = review_files(tmp_path, {
        "product/template/PA.xml": f'<?xml version="1.0"?>\n<productTemplate name="X"><type name="{long_name}"/></productTemplate>\n',
    })
    assert "product/template/PA.xml" in paths_for(review, "PF-GW-NAM-001")


def test_camel_and_snake_secret_names_are_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/SecretNames.gs": '''package gate
class SecretNames {
  var clientSecret = "cs-live-abcdef"
  var privateKey = "pk-live-abcdef"
  var db_password = "db-live-abcdef"
  var auth_token = "tok-live-abcdef"
}
''',
    })
    assert "gsrc/gate/SecretNames.gs" in paths_for(review, "PF-GW-SEC-001")


def test_bearer_prefix_is_not_a_secret(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/TokenBuilder.gs": '''package gate
class TokenBuilder {
  function header() {
    var token = "Bearer " + fetchToken()
    var password = "hunter2"
  }
}
''',
    })
    paths = paths_for(review, "PF-GW-SEC-001")
    assert "gsrc/gate/TokenBuilder.gs" in paths  # the real password is still found


def test_log_string_prose_and_local_variable_are_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/LogStringProse.gs": 'package gate\nclass LogStringProse {\n  var note = "log.error(vehicle.VIN) is forbidden"\n}\n',
        "gsrc/gate/LogVariable.gs": 'package gate\nclass LogVariable {\n  function run(v : PersonalVehicle) { var log = String.format("%s", v.VIN) }\n}\n',
    })
    assert paths_for(review, "PF-GW-LOG-001") == set()


def test_log_getter_and_multiline_are_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/LogGetter.gs": 'package gate\nclass LogGetter {\n  function run(u : User) { log.error("ssn", u.getSSN()) }\n}\n',
        "gsrc/gate/LogParen.gs": 'package gate\nclass LogParen {\n  function run(v : PersonalVehicle) {\n    log.error("note ) inside", v.VIN)\n  }\n}\n',
    })
    assert "gsrc/gate/LogGetter.gs" in paths_for(review, "PF-GW-LOG-001")
    assert "gsrc/gate/LogParen.gs" in paths_for(review, "PF-GW-LOG-001")


def test_system_err_and_document_print(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/SystemErr.gs": 'package gate\nclass SystemErr {\n  function run(e : Exception) { System.err.println(e.Message) }\n}\n',
        "gsrc/gate/DocumentPrint.gs": 'package gate\nclass DocumentPrint {\n  function run(pdf : Document) { pdf.print() }\n}\n',
    })
    assert "gsrc/gate/SystemErr.gs" in paths_for(review, "PF-GW-LOG-002")
    assert "gsrc/gate/DocumentPrint.gs" not in paths_for(review, "PF-GW-LOG-002")


def test_custom_create_statement_method_is_not_sql(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/StatementBuilder.gs": 'package gate\nclass StatementBuilder {\n  function createStatement(text : String) : String { return text }\n}\n',
    })
    assert paths_for(review, "PF-GW-SQL-001") == set()


def test_plural_template_and_gtests_paths_are_classified(tmp_path: Path) -> None:
    long_name = "A" * 25
    review = review_files(tmp_path, {
        "product/templates/PersonalAuto.xml": f'<?xml version="1.0"?>\n<productTemplate name="X"><type name="{long_name}"/></productTemplate>\n',
        "product/PersonalAutoTemplate/PA.xml": f'<?xml version="1.0"?>\n<productTemplate name="Y"><type name="{long_name}"/></productTemplate>\n',
        "gtests/gate/RatingChecks.gs": 'package gate\nclass RatingChecks extends GUnitTestClassBase {\n  function check() { Query.make(PersonalVehicle) }\n}\n',
    })
    assert "product/templates/PersonalAuto.xml" in paths_for(review, "PF-GW-NAM-001")
    assert "product/PersonalAutoTemplate/PA.xml" in paths_for(review, "PF-GW-NAM-001")
    assert "gtests/gate/RatingChecks.gs" in paths_for(review, "PF-GW-GUNIT-001")


def test_root_product_model_sbt_is_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "ProductModel.xml": '<?xml version="1.0"?>\n<productModel name="X" standardsBasedTemplate="true"/>\n',
    })
    assert len(review.readiness) == 1


def test_two_commits_in_one_bundle_are_both_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/DoubleCommit.gs": '''package gate
class DoubleCommit {
  function save(a : PersonalVehicle, b : PersonalVehicle) {
    gw.transaction.Transaction.runWithNewBundle(\\bundle -> {
      bundle.add(a)
      bundle.commit()
      bundle.add(b)
      bundle.commit()
    })
  }
}
''',
    })
    matches = [f for f in review.findings if f.rule_id == "PF-GW-TX-001"]
    assert len(matches) == 2


def test_custom_receiver_statement_calls_are_not_sql(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/CustomDao.gs": '''package gate
class CustomDao {
  function run(dao : CustomDao) {
    dao.createStatement("hello")
    dao.prepareStatement("hello")
  }
}
''',
    })
    assert paths_for(review, "PF-GW-SQL-001") == set()


def test_safe_suffix_secret_names_are_not_flagged(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/SafeNames.gs": '''package gate
class SafeNames {
  var tokenUrl = "https://example.test/token"
  var passwordPolicy = "standard-policy"
  var secretName = "primary"
  var tokenEndpoint = "https://example.test"
}
''',
    })
    assert paths_for(review, "PF-GW-SEC-001") == set()


def test_multiple_secrets_are_found_and_all_values_redacted(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/MultiSecret.gs": '''package gate
class MultiSecret {
  var apiKey = "sk-live-aaa111"
  var password = "hunter2"
  var clientSecret = "cs-live-bbb222"
}
''',
    })
    matches = [f for f in review.findings if f.rule_id == "PF-GW-SEC-001"]
    assert len(matches) == 3
    for finding in matches:
        for evidence_id in finding.evidence_ids:
            ev = next(e for e in review.evidence if e.evidence_id == evidence_id)
            assert "hunter2" not in ev.excerpt
            assert "sk-live-aaa111" not in ev.excerpt
            assert "cs-live-bbb222" not in ev.excerpt


def test_parameter_property_secret_is_detected(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/ParamSecret.gs": '''package gate
class ParamSecret {
  function set(c : Config) { c.password = "hunter2" }
}
''',
    })
    assert "gsrc/gate/ParamSecret.gs" in paths_for(review, "PF-GW-SEC-001")


def test_non_sec_finding_excerpt_redacts_adjacent_secret_in_persisted_artifacts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"

    def write(rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    write(
        "config/web/pcf/policy/PAVehicleDV.pcf",
        '<?xml version="1.0"?>\n'
        '<PCF name="PAVehicleDV"><Screen>'
        '<TypeKeyInput id="VehicleType" value="VehicleType"/>'
        "</Screen></PCF>\n",
    )
    write(
        "config/metadata/entity/PersonalVehicle.eti",
        '<?xml version="1.0"?>\n'
        '<entity name="PersonalVehicle"><column name="VIN" type="Text"/></entity>\n',
    )
    # The class-line discovery excerpt contains hunter2. The SQL finding's
    # three-line review excerpt contains the adjacent apiKey assignment.
    write(
        "gsrc/acme/PersonalVehicleValidation.gs",
        """package acme
class PersonalVehicleValidation {
  var password = "hunter2"
  function find() {
    DriverManager.getConnection("jdbc:acme")
    var apiKey = "sk-live-LEAK123"
  }
}
""",
    )

    store = RunStore(tmp_path / "data")
    store.create_run("R-LEAK", project_id="test", snapshot_id="S-LEAK")
    result = execute_run(
        root, store, "R-LEAK", project_id="test", fixture_id="uploaded", tier="demo",
    )
    assert any(f.rule_id == "PF-GW-SQL-001" for f in result.review.findings)

    raw_secrets = ("hunter2", "sk-live-LEAK123")
    for name in ("evidence.json", "review_evidence.json", "findings.json",
                 "packet.json", "packet.html"):
        text = (store.run_dir("R-LEAK") / name).read_text(encoding="utf-8")
        for secret in raw_secrets:
            assert secret not in text, (name, secret)

    review_evidence = store.read_artifact("R-LEAK", "review_evidence.json")["evidence"]
    sql_finding = next(
        finding for finding in store.read_artifact("R-LEAK", "findings.json")["findings"]
        if finding["rule_id"] == "PF-GW-SQL-001"
    )
    sql_evidence = next(
        item for item in review_evidence if item["evidence_id"] == sql_finding["evidence_ids"][0]
    )
    assert sql_evidence["locator"]["line"] == 5
    assert "[REDACTED:" in sql_evidence["excerpt"]
    assert "[REDACTED:" in (store.run_dir("R-LEAK") / "packet.html").read_text(encoding="utf-8")


def test_adjacent_comment_and_escaped_quote_values_are_redacted(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/gate/Leaky.gs": '''package gate
class Leaky {
  var apiKey = "sk-live-aaa111"
  var password = "hunter2"
  var clientSecret = "cs-live-bbb222"
  // staging password is hunter2
  var escaped = "aaa\\"bbb"
}
''',
    })
    raw_values = ["sk-live-aaa111", "hunter2", "cs-live-bbb222", 'aaa\\"bbb']
    for finding in review.findings:
        if finding.rule_id != "PF-GW-SEC-001":
            continue
        for evidence_id in finding.evidence_ids:
            ev = next(e for e in review.evidence if e.evidence_id == evidence_id)
            for value in raw_values:
                assert value not in ev.excerpt, (value, ev.excerpt)
