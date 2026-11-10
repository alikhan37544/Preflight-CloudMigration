"""Contract tests for intake: manifest, hashing, classification, zip safety.

Written before app/services/intake.py exists.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import stat
import time
import warnings
import zipfile
from pathlib import Path

import pytest

from app.services.intake import (
    UnsafeArchiveError,
    build_manifest,
    check_source_immutable,
    classify_path,
    safe_extract_zip,
    snapshot_hash,
)

REPO = Path(__file__).resolve().parents[1]


def test_manifest_lists_every_file_with_matching_hash(manifest_fixture: Path) -> None:
    manifest = build_manifest(manifest_fixture, snapshot_id="S-1", project_id="P-1")
    paths = {a.path for a in manifest.artifacts}
    on_disk = {
        p.relative_to(manifest_fixture).as_posix()
        for p in manifest_fixture.rglob("*")
        if p.is_file()
    }
    assert paths == on_disk
    assert manifest.file_count == len(on_disk)
    assert all(len(a.sha256) == 64 for a in manifest.artifacts)


def test_manifest_classifies_known_kinds(manifest_fixture: Path) -> None:
    manifest = build_manifest(manifest_fixture, snapshot_id="S-1", project_id="P-1")
    by_path = {a.path: a for a in manifest.artifacts}
    assert by_path["config/web/pcf/policy/PAVehicleDV.pcf"].kind == "pcf"
    assert by_path["config/metadata/entity/PersonalVehicle.eti"].kind == "entity"
    assert by_path["config/extensions/entity/PersonalVehicle.etx"].kind == "entity_extension"
    assert by_path["config/metadata/typelist/VehicleType.tti"].kind == "typelist"
    assert by_path["config/extensions/typelist/VehicleType.ttx"].kind == "typelist_extension"
    assert by_path["gsrc/acme/validation/PersonalVehicleValidation.gs"].kind == "gosu"
    assert by_path["assets/logo.png"].status.value == "binary"
    assert by_path["config/broken.xml"].status.value == "corrupt"
    assert by_path["README.txt"].status.value == "parsed"
    assert by_path["README.txt"].kind == "text"


def test_manifest_lists_unsupported_and_corrupt_explicitly(manifest_fixture: Path) -> None:
    manifest = build_manifest(manifest_fixture, snapshot_id="S-1", project_id="P-1")
    assert "assets/logo.png" in manifest.unsupported_paths
    assert "config/broken.xml" in manifest.unsupported_paths
    assert "README.txt" not in manifest.unsupported_paths
    assert "unsupported files are listed, not hidden" in manifest.notice.lower() or manifest.unsupported_paths


def test_snapshot_hash_is_stable_across_mtime_changes(manifest_fixture: Path) -> None:
    first = snapshot_hash(manifest_fixture)
    for path in manifest_fixture.rglob("*"):
        if path.is_file():
            os.utime(path, (1_700_000_000, 1_700_000_000))
    second = snapshot_hash(manifest_fixture)
    assert first == second
    assert len(first) == 64


def test_snapshot_hash_changes_when_content_changes(manifest_fixture: Path) -> None:
    first = snapshot_hash(manifest_fixture)
    (manifest_fixture / "README.txt").write_text("changed\n", encoding="utf-8")
    second = snapshot_hash(manifest_fixture)
    assert first != second


def test_source_immutable_passes_when_unchanged(manifest_fixture: Path) -> None:
    digest = snapshot_hash(manifest_fixture)
    assert check_source_immutable(manifest_fixture, digest) is True


def test_source_immutable_detects_write(manifest_fixture: Path) -> None:
    digest = snapshot_hash(manifest_fixture)
    (manifest_fixture / "config/web/pcf/policy/PAVehicleDV.pcf").write_text("<PCF/>", encoding="utf-8")
    assert check_source_immutable(manifest_fixture, digest) is False


@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "/abs/evil.txt", "a/../../evil.txt", "C:/evil.txt", "a\\..\\evil.txt"],
)
def test_safe_extract_rejects_zip_slip(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, "boom")
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out")


def test_safe_extract_rejects_nul_and_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ok.txt", "ok")
        info = zipfile.ZipInfo("link.txt")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "target")
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out")


def test_safe_extract_rejects_high_compression_ratio(tmp_path: Path) -> None:
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.txt", "0" * (2 * 1024 * 1024))
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out", max_ratio=50)


def test_safe_extract_writes_normal_archive(tmp_path: Path) -> None:
    archive = tmp_path / "ok.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("config/a.pcf", "<PCF name=\"A\"/>")
        zf.writestr("README.txt", "hi")
    out = safe_extract_zip(archive, tmp_path / "out")
    assert (out / "config/a.pcf").is_file()
    assert (out / "README.txt").read_text(encoding="utf-8") == "hi"


def test_zip_entry_count_limit(tmp_path: Path) -> None:
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(5):
            zf.writestr(f"f{i}.txt", "x")
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out", max_files=4)


def test_classify_path_is_pure() -> None:
    assert classify_path("a/b/Vehicle.pcf")[0] == "pcf"
    assert classify_path("a/b/Vehicle.eti")[0] == "entity"
    assert classify_path("a/b/unknown.zzz")[0] is None


def test_classify_path_uses_path_segments_for_templates_and_tests() -> None:
    assert classify_path("product/template/PA.xml")[0] == "template_xml"
    assert classify_path("gtest/adv/RatingChecks.gs")[0] == "gunit"
    assert classify_path("gsrc/adv/Contest.gs")[0] == "gosu"
    assert classify_path("config/resources/productmodel/X.xml")[0] == "product_xml"


# -- intake hardening -------------------------------------------------------


def test_manifest_lists_symlinks_as_unsupported(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("must not be read", encoding="utf-8")
    (root / "README.txt").write_text("hello\n", encoding="utf-8")
    (root / "link.txt").symlink_to(secret)
    (root / "dangling.txt").symlink_to(tmp_path / "missing.txt")

    manifest = build_manifest(root, snapshot_id="S-1", project_id="P-1")
    by_path = {artifact.path: artifact for artifact in manifest.artifacts}
    for name in ("link.txt", "dangling.txt"):
        assert by_path[name].status.value == "unsupported"
        assert by_path[name].kind == "symlink"
        assert by_path[name].warnings
        assert len(by_path[name].sha256) == 64
        assert name in manifest.unsupported_paths
        assert any(name in warning for warning in manifest.warnings)
    assert by_path["README.txt"].status.value == "parsed"


def test_malformed_json_and_yaml_are_corrupt_not_parsed(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "bad.json").write_text('{"broken": ', encoding="utf-8")
    (root / "bad.yaml").write_text("types: [unterminated\n", encoding="utf-8")
    (root / "tagged.yaml").write_text(
        "value: !<tag:yaml.org,2002:python/object/apply:os.system> ['true']\n",
        encoding="utf-8",
    )
    (root / "good.json").write_text('{"ok": true}\n', encoding="utf-8")
    (root / "good.yaml").write_text("types:\n  PAVehicle:\n    nameOverride: PersonalVehicle\n",
                                    encoding="utf-8")

    manifest = build_manifest(root, snapshot_id="S-1", project_id="P-1")
    by_path = {artifact.path: artifact for artifact in manifest.artifacts}
    for name in ("bad.json", "bad.yaml", "tagged.yaml"):
        assert by_path[name].status.value == "corrupt"
        assert by_path[name].warnings
        assert name in manifest.unsupported_paths
        assert any(name in warning for warning in manifest.warnings)
    assert by_path["good.json"].status.value == "parsed"
    assert by_path["good.yaml"].status.value == "parsed"


def test_line_count_handles_trailing_newline(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "one.txt").write_text("a\n", encoding="utf-8")
    (root / "two.txt").write_text("a\nb", encoding="utf-8")
    (root / "two_nl.txt").write_text("a\nb\n", encoding="utf-8")
    (root / "empty.txt").write_text("", encoding="utf-8")
    manifest = build_manifest(root, snapshot_id="S-1", project_id="P-1")
    by_path = {artifact.path: artifact for artifact in manifest.artifacts}
    assert by_path["one.txt"].line_count == 1
    assert by_path["two.txt"].line_count == 2
    assert by_path["two_nl.txt"].line_count == 2
    assert by_path["empty.txt"].line_count == 0


@pytest.mark.parametrize("name", ["", ".", "./", "a/./b", "a//b"])
def test_safe_extract_rejects_empty_or_dot_entries(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, "boom")
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out")


def test_safe_extract_rejects_hardlink_metadata(tmp_path: Path) -> None:
    archive = tmp_path / "hardlink.zip"
    info = zipfile.ZipInfo("hard.txt")
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    target = b"target.txt"
    info.extra = (
        (0x000D).to_bytes(2, "little")
        + (12 + len(target)).to_bytes(2, "little")
        + b"\x00" * 12
        + target
    )
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "data")
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out")


def test_safe_extract_applies_ratio_to_small_entries(tmp_path: Path) -> None:
    archive = tmp_path / "small-bomb.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.txt", "0" * 2048)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out", max_ratio=50)


def test_safe_extract_enforces_per_entry_size_limit(tmp_path: Path) -> None:
    archive = tmp_path / "big-entry.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("big.txt", "x" * 2048)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out", max_entry_uncompressed=1024)


def test_safe_extract_enforces_total_size_limit(tmp_path: Path) -> None:
    archive = tmp_path / "big-total.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "x" * 800)
        zf.writestr("b.txt", "y" * 800)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(
            archive, tmp_path / "out",
            max_entry_uncompressed=1000, max_uncompressed=1000,
        )


def test_unreadable_file_is_recorded_and_does_not_abort(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read chmod-000 files")
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "README.txt").write_text("ok\n", encoding="utf-8")
    unreadable = root / "locked.txt"
    unreadable.write_text("secret\n", encoding="utf-8")
    os.chmod(unreadable, 0)
    try:
        manifest = build_manifest(root, snapshot_id="S-1", project_id="P-1")
        by_path = {artifact.path: artifact for artifact in manifest.artifacts}
        artifact = by_path["locked.txt"]
        assert artifact.status.value == "unsupported"
        assert "unreadable: PermissionError" in artifact.warnings[0]
        assert "locked.txt" in manifest.unsupported_paths
        assert any("unreadable: PermissionError" in warning for warning in manifest.warnings)
        assert by_path["README.txt"].status.value == "parsed"
        assert snapshot_hash(root) == manifest.sha256
    finally:
        os.chmod(unreadable, 0o600)


def test_unreadable_directory_is_recorded_and_does_not_abort(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can list chmod-000 directories")
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "README.txt").write_text("ok\n", encoding="utf-8")
    locked = root / "locked"
    locked.mkdir()
    (locked / "inside.txt").write_text("hidden\n", encoding="utf-8")
    os.chmod(locked, 0)
    try:
        manifest = build_manifest(root, snapshot_id="S-1", project_id="P-1")
        by_path = {artifact.path: artifact for artifact in manifest.artifacts}
        artifact = by_path["locked"]
        assert artifact.kind == "directory"
        assert artifact.status.value == "unsupported"
        assert "unreadable: PermissionError" in artifact.warnings[0]
        assert "locked" in manifest.unsupported_paths
        assert any("unreadable: PermissionError" in warning for warning in manifest.warnings)
        assert by_path["README.txt"].status.value == "parsed"
        assert snapshot_hash(root) == manifest.sha256
    finally:
        os.chmod(locked, 0o700)


def test_special_files_are_recorded_as_unsupported(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "README.txt").write_text("ok\n", encoding="utf-8")
    os.mkfifo(root / "pipe")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(root / "socket"))
        manifest = build_manifest(root, snapshot_id="S-1", project_id="P-1")
    finally:
        sock.close()

    by_path = {artifact.path: artifact for artifact in manifest.artifacts}
    for name, kind in (("pipe", "fifo"), ("socket", "socket")):
        artifact = by_path[name]
        assert artifact.kind == kind
        assert artifact.status.value == "unsupported"
        assert "special file type" in artifact.warnings[0]
        assert name in manifest.unsupported_paths
    assert by_path["README.txt"].status.value == "parsed"
    assert snapshot_hash(root) == manifest.sha256


def test_non_utf8_filename_is_sanitized_not_crashing(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    raw_path = os.fsencode(str(root)) + b"/bad-\xff.txt"
    descriptor = os.open(raw_path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, b"content\n")
    finally:
        os.close(descriptor)

    manifest = build_manifest(root, snapshot_id="S-1", project_id="P-1")
    by_path = {artifact.path: artifact for artifact in manifest.artifacts}
    assert "bad-\\xff.txt" in by_path
    assert by_path["bad-\\xff.txt"].status.value == "parsed"
    payload = manifest.model_dump(mode="json")
    assert payload["artifacts"][0]["path"] == "bad-\\xff.txt"
    assert json.dumps(payload)
    assert snapshot_hash(root) == manifest.sha256


def test_safe_extract_rejects_deep_entry_without_partial_files(tmp_path: Path) -> None:
    archive = tmp_path / "deep.zip"
    deep_name = "/".join(["d"] * 900) + "/x.txt"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("normal.txt", "ok")
        zf.writestr(deep_name, "boom")

    out = tmp_path / "out"
    with pytest.raises(UnsafeArchiveError, match="path exceeds"):
        safe_extract_zip(archive, out)
    assert not out.exists()
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == [archive]


def test_safe_extract_converts_oserror_and_cleans_up(tmp_path: Path) -> None:
    archive = tmp_path / "long-name.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("normal.txt", "ok")
        zf.writestr("a" * 300 + ".txt", "boom")

    out = tmp_path / "out"
    with pytest.raises(UnsafeArchiveError, match="could not be extracted"):
        safe_extract_zip(archive, out)
    assert not out.exists()


def test_manifest_parser_warning_redacts_secrets_before_persisting(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.store import RunStore

    root = tmp_path / "snapshot"
    root.mkdir()
    live_secret = "sk-live-SECRET123"
    plain_secret = "hunter2"
    (root / "bad-live.yaml").write_text(
        f'types: [unterminated\npassword: "{live_secret}"\n', encoding="utf-8"
    )
    (root / "bad-plain.yaml").write_text(
        f'password: "{plain_secret}"\n  nested: bad\n', encoding="utf-8"
    )
    manifest = build_manifest(root, snapshot_id="S-LEAK", project_id="P-LEAK")

    dumped = json.dumps(manifest.model_dump(mode="json"))
    assert live_secret not in dumped
    assert plain_secret not in dumped
    assert "[REDACTED:" in dumped

    store = RunStore(tmp_path / "data")
    store.create_run("R-LEAK", project_id="demo", snapshot_id="S-LEAK")
    store.write_artifact("R-LEAK", "manifest.json", manifest.model_dump(mode="json"))
    store.update_status("R-LEAK", status="succeeded", stage="succeeded", percent=100.0)
    client = TestClient(create_app(Settings(
        data_dir=tmp_path / "data", fixtures_dir=REPO / "fixtures", secret_key="intake-test",
    )))
    response = client.get("/manifest?run=R-LEAK")
    assert response.status_code == 200
    assert live_secret not in response.text
    assert plain_secret not in response.text
    assert "[REDACTED:" in response.text


def test_yaml_secret_styles_never_reach_manifest_or_packet_html(
    tmp_path: Path, tiny_snapshot: Path
) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.services.pipeline import execute_run
    from app.store import RunStore

    root = tmp_path / "leak-snapshot"
    shutil.copytree(tiny_snapshot, root)
    leaked = {
        "leak-unquoted.yaml": ("Zx9Qw2Lm7Pk4Vn8Rt", "types:\n  password: Zx9Qw2Lm7Pk4Vn8Rt: extra\n"),
        "leak-single.yaml": ("Pl8Kj3Hn5Gf2Ds9Wq", "password: 'Pl8Kj3Hn5Gf2Ds9Wq'\n  bad: [\n"),
        "leak-double.yaml": ("Mn4Bv7Cx1Za6Qw2E", 'api_key: "Mn4Bv7Cx1Za6Qw2E"\n  bad: [\n'),
        "leak-colon.yaml": (
            "Vc5RtY8Ui3Op2As",
            "password: user:Vc5RtY8Ui3Op2As:more: extra\n",
        ),
        "leak-tab.yaml": ("Tb6Yh9Nj4Mk1Lp3Q", "\tcredential:\tTb6Yh9Nj4Mk1Lp3Q\n"),
        "leak-escape.yaml": (
            "Bd3Fg6Hj9Kl2Zx5C",
            'client_secret: "Bd3Fg6Hj9Kl2Zx5C\\qtail"\n',
        ),
        "leak-unterminated.yaml": (
            "Un7Term8Inated0Value",
            'password: "Un7Term8Inated0Value\n',
        ),
    }
    for name, (_, text) in leaked.items():
        (root / name).write_text(text, encoding="utf-8")

    manifest = build_manifest(root, snapshot_id="S-YAML", project_id="P-YAML")
    dumped = json.dumps(manifest.model_dump(mode="json"))
    for secret, _ in leaked.values():
        assert secret not in dumped
    assert "[REDACTED:" in dumped

    data = tmp_path / "data"
    store = RunStore(data)
    store.create_run("R-YAML-LEAK", project_id="demo", snapshot_id="S-YAML")
    execute_run(root, store, "R-YAML-LEAK", project_id="demo",
                fixture_id="uploaded", tier="demo")
    run_dir = store.run_dir("R-YAML-LEAK")
    for name in ("manifest.json", "packet.json", "packet.html"):
        text = (run_dir / name).read_text(encoding="utf-8")
        for secret, _ in leaked.values():
            assert secret not in text, (name, secret)

    client = TestClient(create_app(Settings(
        data_dir=data, fixtures_dir=REPO / "fixtures", secret_key="yaml-leak-test",
    )))
    response = client.get("/manifest?run=R-YAML-LEAK")
    assert response.status_code == 200
    for secret, _ in leaked.values():
        assert secret not in response.text
    assert "[REDACTED:" in response.text


def test_snapshot_hash_tracks_symlink_retargeting(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "README.txt").write_text("hello\n", encoding="utf-8")
    first_target = tmp_path / "first.txt"
    second_target = tmp_path / "second.txt"
    first_target.write_text("same-content\n", encoding="utf-8")
    second_target.write_text("same-content\n", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(first_target)

    first = snapshot_hash(root)
    assert snapshot_hash(root) == first  # stable when nothing changes

    link.unlink()
    link.symlink_to(second_target)
    second = snapshot_hash(root)
    assert second != first

    link.unlink()
    link.symlink_to(first_target)
    assert snapshot_hash(root) == first


def test_safe_extract_rejects_duplicate_member_names(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("dup.txt", "first")
            zf.writestr("dup.txt", "last")
    with pytest.raises(UnsafeArchiveError, match="duplicate"):
        safe_extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "out" / "dup.txt").exists()


def test_safe_extract_rejects_file_and_directory_name_collision(tmp_path: Path) -> None:
    archive = tmp_path / "collision.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("node", "file")
            zf.writestr("node/", "directory")
    with pytest.raises(UnsafeArchiveError, match="duplicate"):
        safe_extract_zip(archive, tmp_path / "out")


def test_safe_extract_rejects_many_small_bomb_entries_before_writing(tmp_path: Path) -> None:
    archive = tmp_path / "many-small-bomb.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for index in range(200):
            zf.writestr(f"entry-{index}.txt", "0" * 2048)

    out = tmp_path / "out"
    started = time.monotonic()
    with pytest.raises(UnsafeArchiveError, match="uncompressed archive exceeds"):
        safe_extract_zip(
            archive, out,
            max_ratio=100_000,
            max_entry_uncompressed=4096,
            max_uncompressed=100_000,
        )
    elapsed = time.monotonic() - started
    assert elapsed < 2.0
    assert [path for path in out.rglob("*") if path.is_file()] == []
