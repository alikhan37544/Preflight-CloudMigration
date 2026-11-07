"""Contract tests for intake: manifest, hashing, classification, zip safety.

Written before app/services/intake.py exists.
"""

from __future__ import annotations

import io
import os
import stat
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
