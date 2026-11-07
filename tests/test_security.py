"""Security contract tests: host/origin, XXE, YAML tags, XSS autoescape.

Written before the security gate is considered complete.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.parsers.config import parse_config_yaml
from app.services.parsers.entity import parse_entity
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", fixtures_dir=REPO / "fixtures",
                        sync_runs=True, secret_key="security-test")
    return TestClient(create_app(settings))


def test_host_header_allowlist(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400


def test_origin_allowlist(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/", headers={"Origin": "https://evil.example"}).status_code == 400


def test_xml_external_entity_is_not_expanded(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    path = tmp_path / "Evil.eti"
    path.write_text(
        f"""<?xml version="1.0"?>
<!DOCTYPE entity [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]>
<entity name="Evil">
  <column name="&xxe;" type="Text"/>
</entity>
""",
        encoding="utf-8",
    )
    try:
        parsed = parse_entity(path)
    except Exception:
        return  # rejecting the document is acceptable
    for column in parsed.columns:
        assert "TOP-SECRET" not in column.name
        assert "TOP-SECRET" not in column.excerpt


def test_yaml_arbitrary_tags_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "evil.yaml"
    path.write_text("value: !!python/object/apply:os.system ['touch /tmp/pwned']\n", encoding="utf-8")
    with pytest.raises(Exception):
        parse_config_yaml(path)


def test_manifest_autoescapes_malicious_filenames(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "data")
    store.create_run("R-XSS", project_id="demo", snapshot_id="S-XSS")
    store.write_artifact("R-XSS", "manifest.json", {
        "schema_version": "1.0", "snapshot_id": "S-XSS", "project_id": "demo",
        "sha256": "a" * 64, "file_count": 1, "total_size": 10,
        "unsupported_paths": [], "notice": "listed",
        "artifacts": [{
            "schema_version": "1.0", "path": "<script>alert(1)</script>.pcf",
            "sha256": "b" * 64, "size": 10, "kind": "pcf", "parser": "pcf",
            "status": "parsed", "warnings": [], "line_count": 1,
        }],
    })
    store.update_status("R-XSS", status="succeeded", stage="succeeded", percent=100.0)
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data",
                                            fixtures_dir=REPO / "fixtures",
                                            secret_key="security-test")))
    response = client.get("/manifest?run=R-XSS")
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_security_headers_on_all_pages(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_zip_slip_upload_is_rejected(tmp_path: Path) -> None:
    import io
    import zipfile

    client = make_client(tmp_path)
    home = client.get("/")
    import re

    token = re.search(r'name="csrf-token" content="([^"]+)"', home.text).group(1)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("../evil.txt", "boom")
    response = client.post(
        "/api/imports",
        files={"file": ("evil.zip", buffer.getvalue(), "application/zip")},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 400
    assert "parent-traversal" in response.json()["detail"] or "escape" in response.json()["detail"]
