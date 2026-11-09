"""Contract tests for intake: manifest, hashing, classification, zip safety.

Written before app/services/intake.py exists.
"""

from __future__ import annotations

import io
import json
import os
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
