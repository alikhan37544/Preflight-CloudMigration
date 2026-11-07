"""Explicit false-positive gate for the review rules.

Each case is a deliberate near-miss that a naive regex would flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.discovery import DiscoveryResult
from app.services.intake import build_manifest
from app.services.review import run_review


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


def test_catch_with_logging_is_not_swallowed(tmp_path: Path) -> None:
    review = review_files(tmp_path, {
        "gsrc/acme/CatchLogs.gs": '''package acme
class CatchLogs {
  function run() {
    try { risky() } catch (e : Exception) { log.error(e.Message) }
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
