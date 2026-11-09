"""Security contract tests: host/origin, XXE, YAML tags, XSS autoescape.

Written before the security gate is considered complete.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import csrf_for
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


# -- secret key, host/origin, CSRF, session cookie -------------------------


def _csrf_token(client: TestClient) -> str:
    home = client.get("/")
    match = re.search(r'name="csrf-token" content="([^"]+)"', home.text)
    assert match
    return match.group(1)


def test_secret_key_fallback_is_random_and_env_overridable(monkeypatch) -> None:
    monkeypatch.delenv("PREFLIGHT_SECRET_KEY", raising=False)
    first = Settings().secret_key
    second = Settings().secret_key
    assert first == second  # one per-process fallback
    assert first != "local-development-secret"
    assert len(first) >= 32
    monkeypatch.setenv("PREFLIGHT_SECRET_KEY", "explicit-test-secret")
    assert Settings().secret_key == "explicit-test-secret"


@pytest.mark.parametrize("host", ["", " "])
def test_empty_host_header_is_rejected(tmp_path: Path, host: str) -> None:
    client = make_client(tmp_path)
    assert client.get("/", headers={"Host": host}).status_code == 400


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1:9999",
        "https://127.0.0.1:8000",
        "http://localhost:8001",
        "http://testserver:8000",
    ],
)
def test_origin_requires_exact_scheme_host_and_port(tmp_path: Path, origin: str) -> None:
    client = make_client(tmp_path)
    assert client.get("/", headers={"Origin": origin}).status_code == 400


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:8000", "http://localhost:8000", "http://testserver"],
)
def test_loopback_origins_are_accepted(tmp_path: Path, origin: str) -> None:
    client = make_client(tmp_path)
    assert client.get("/", headers={"Origin": origin}).status_code == 200


def test_exact_same_origin_on_alternate_port_is_accepted(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get(
        "/", headers={"Host": "127.0.0.1:8123", "Origin": "http://127.0.0.1:8123"}
    )
    assert response.status_code == 200



def test_allowed_origins_are_configurable(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data", fixtures_dir=REPO / "fixtures",
        secret_key="security-test", allowed_origins=("http://127.0.0.1:8123",),
    )
    client = TestClient(create_app(settings))
    assert client.get("/", headers={"Origin": "http://127.0.0.1:8123"}).status_code == 200
    assert client.get("/", headers={"Origin": "http://127.0.0.1:8000"}).status_code == 400


def test_csrf_token_in_query_string_is_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = _csrf_token(client)
    response = client.post(
        f"/api/runs?csrf_token={token}",
        json={"project_id": "demo", "fixture_id": "demo-slice-300"},
    )
    assert response.status_code == 403


def test_csrf_header_is_accepted(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = _csrf_token(client)
    response = client.post(
        "/api/runs/R-MISSING/decisions",
        json={"object_type": "mapping", "object_id": "M-1", "action": "accept", "reason": "x"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 404  # CSRF passed; the run is simply absent


def test_csrf_form_field_is_accepted(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = _csrf_token(client)
    response = client.post(
        "/api/imports",
        files={
            "file": ("bad.zip", b"not a zip", "application/zip"),
            "csrf_token": (None, token),
        },
    )
    assert response.status_code == 400
    assert "not a valid zip" in response.json()["detail"]


def test_unsigned_session_cookie_is_replaced(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.cookies.set("pf_session", "attacker-chosen")
    response = client.get("/")
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "pf_session=" in set_cookie
    assert "pf_session=attacker-chosen" not in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()
    token = re.search(r'name="csrf-token" content="([^"]+)"', response.text).group(1)
    assert token != csrf_for("attacker-chosen", "security-test")


@pytest.mark.parametrize(
    "payload",
    [
        "value: !!python/object/apply:os.system ['true']\n",
        "value: !python/object/apply:os.system ['true']\n",
        "value: !<tag:yaml.org,2002:python/object/apply:os.system> ['true']\n",
        "value: !<tag:example.com,2020:custom> x\n",
    ],
)
def test_all_explicit_yaml_tags_are_rejected(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "evil.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        parse_config_yaml(path)


def test_safe_yaml_config_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "types:\n  PAVehicle:\n    nameOverride: PersonalVehicle\n"
        "note: '!! is plain text here'\n",
        encoding="utf-8",
    )
    parsed = parse_config_yaml(path)
    assert parsed.data["types"]["PAVehicle"]["nameOverride"] == "PersonalVehicle"
    assert parsed.data["note"] == "!! is plain text here"
