"""Snapshot intake, hashing, classification, and archive safety.

The source snapshot is always treated as read-only. Intake never writes under
the snapshot root; callers can verify immutability with snapshot_hash().
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path

from lxml import etree

from app.models import Artifact, ArtifactStatus, Manifest
from app.services.parsers.config import parse_config_yaml

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".bin", ".class", ".jar",
    ".zip", ".gz", ".tgz", ".7z", ".woff", ".woff2", ".ttf", ".otf", ".so",
    ".xls", ".xlsx", ".doc", ".docx",
}
TEXT_SUFFIXES = {".txt", ".md", ".properties", ".log"}
XML_SUFFIXES = {".pcf", ".eti", ".etx", ".tti", ".ttx", ".xml", ".xsd", ".wsdl"}
GOSU_SUFFIXES = {".gs", ".gsx"}
YAML_SUFFIXES = {".yaml", ".yml"}
JSON_SUFFIXES = {".json"}

_ZIP_DRIVE = re.compile(r"^[A-Za-z]:")


class UnsafeArchiveError(ValueError):
    """Raised when an uploaded archive violates the intake safety contract."""


def _kind_for(path: str) -> tuple[str | None, str | None]:
    lower = path.replace("\\", "/").lower()
    segments = lower.split("/")
    name = segments[-1]
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""

    if suffix == ".pcf":
        return "pcf", "pcf"
    if suffix == ".eti":
        return "entity", "entity"
    if suffix == ".etx":
        return "entity_extension", "entity"
    if suffix == ".tti":
        return "typelist", "typelist"
    if suffix == ".ttx":
        return "typelist_extension", "typelist"
    if suffix in GOSU_SUFFIXES:
        if any(segment.startswith("gtest") for segment in segments):
            return "gunit", "gosu"
        return "gosu", "gosu"
    if suffix in YAML_SUFFIXES:
        if "codegen_config" in name:
            return "codegen_yaml", "config"
        if "template_gen_config" in name:
            return "template_gen_config_yaml", "config"
        return "config_yaml", "config"
    if suffix in JSON_SUFFIXES:
        if "schema" in name or "/schemas/" in lower:
            return "api_schema", "json"
        if "mapping" in name:
            return "api_mapping", "json"
        if "updater" in name:
            return "api_updater", "json"
        return "json", "json"
    if suffix == ".xml":
        if "template_gen_config" in name:
            return "template_gen_config", "xml"
        if any("template" in segment for segment in segments):
            return "template_xml", "product"
        if any("productmodel" in segment or "product_model" in segment for segment in segments) or "product" in segments:
            return "product_xml", "product"
        if "productmodel" in name or "product_model" in name:
            return "product_xml", "product"
        return "xml", "xml"
    if suffix in XML_SUFFIXES:
        return "xml", "xml"
    if suffix in BINARY_SUFFIXES:
        return "binary", None
    if suffix in TEXT_SUFFIXES:
        return "text", "text"
    return None, None


def classify_path(path: str) -> tuple[str | None, str | None]:
    """Return (kind, parser) for a relative path. Pure function."""
    return _kind_for(path.replace("\\", "/"))


def _safe_xml_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        recover=False,
    )


def _looks_binary(data: bytes) -> bool:
    sample = data[:8192]
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_hash(root: Path) -> str:
    """SHA-256 over sorted (relative_path, file_sha256) pairs.

    Modification times are deliberately excluded so repeated runs are
    reproducible across copies.
    """
    pairs: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            pairs.append((path.relative_to(root).as_posix(), _sha256_bytes(data)))
    payload = json.dumps(pairs, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_manifest(root: Path, *, snapshot_id: str, project_id: str) -> Manifest:
    if not root.is_dir():
        raise FileNotFoundError(root)

    artifacts: list[Artifact] = []
    unsupported: list[str] = []
    total_size = 0
    warnings: list[str] = []

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            # Never follow links, but never hide them either: they are listed
            # as explicit unsupported artifacts with a warning.
            try:
                target = os.readlink(path)
            except OSError:
                target = ""
            target_bytes = target.encode("utf-8", "surrogateescape")
            artifacts.append(
                Artifact(
                    path=rel,
                    sha256=_sha256_bytes(target_bytes),
                    size=len(target_bytes),
                    kind="symlink",
                    parser="none",
                    status=ArtifactStatus.UNSUPPORTED,
                    warnings=["symlink entries are not followed"],
                    line_count=0,
                )
            )
            total_size += len(target_bytes)
            unsupported.append(rel)
            warnings.append(f"{rel}: symlink not followed")
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        total_size += len(data)
        kind, parser = _kind_for(rel)
        status = ArtifactStatus.PARSED
        item_warnings: list[str] = []
        corrupt_label: str | None = None
        line_count = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)

        if kind == "binary" or _looks_binary(data):
            status = ArtifactStatus.BINARY
            if kind is None:
                kind = "binary"
            unsupported.append(rel)
        elif kind is None:
            status = ArtifactStatus.UNSUPPORTED
            kind = "unknown"
            parser = None
            unsupported.append(rel)
        elif parser in {"xml", "pcf", "entity", "typelist"} or rel.lower().endswith(tuple(XML_SUFFIXES)):
            try:
                etree.fromstring(data, _safe_xml_parser())
            except etree.XMLSyntaxError as exc:
                status = ArtifactStatus.CORRUPT
                item_warnings.append(f"XML parse error: {exc}")
                corrupt_label = "XML"
                unsupported.append(rel)
            except ValueError as exc:  # e.g. encoding declaration problems
                status = ArtifactStatus.CORRUPT
                item_warnings.append(f"XML parse error: {exc}")
                corrupt_label = "XML"
                unsupported.append(rel)
        elif parser == "json":
            try:
                json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                status = ArtifactStatus.CORRUPT
                item_warnings.append(f"JSON parse error: {exc}")
                corrupt_label = "JSON"
                unsupported.append(rel)
        elif parser == "config":
            try:
                parse_config_yaml(path)
            except Exception as exc:  # malformed or tagged YAML must not abort intake
                status = ArtifactStatus.CORRUPT
                item_warnings.append(f"YAML parse error: {exc}")
                corrupt_label = "YAML"
                unsupported.append(rel)

        if status is ArtifactStatus.CORRUPT:
            warnings.append(f"{rel}: corrupt {corrupt_label or 'file'}")

        artifacts.append(
            Artifact(
                path=rel,
                sha256=_sha256_bytes(data),
                size=len(data),
                kind=kind or "unknown",
                parser=parser or "none",
                status=status,
                warnings=item_warnings,
                line_count=line_count,
            )
        )

    return Manifest(
        snapshot_id=snapshot_id,
        project_id=project_id,
        sha256=snapshot_hash(root),
        artifacts=artifacts,
        file_count=len(artifacts),
        total_size=total_size,
        unsupported_paths=sorted(unsupported),
        warnings=warnings,
    )


def check_source_immutable(root: Path, expected_hash: str) -> bool:
    return snapshot_hash(root) == expected_hash


def _reject_unsafe_name(name: str) -> None:
    if "\x00" in name:
        raise UnsafeArchiveError(f"archive entry contains NUL: {name!r}")
    normalised = name.replace("\\", "/")
    if name != normalised:
        raise UnsafeArchiveError(f"archive entry contains a backslash: {name!r}")
    if not normalised or normalised in {".", "./"}:
        raise UnsafeArchiveError(f"empty archive entry: {name!r}")
    if normalised.startswith("/"):
        raise UnsafeArchiveError(f"absolute archive entry: {name!r}")
    if _ZIP_DRIVE.match(normalised):
        raise UnsafeArchiveError(f"drive-letter archive entry: {name!r}")
    trimmed = normalised.rstrip("/")
    parts = trimmed.split("/") if trimmed else []
    if not parts:
        raise UnsafeArchiveError(f"empty archive entry: {name!r}")
    if any(part in {"", "."} for part in parts):
        raise UnsafeArchiveError(f"empty or dot path segment in archive entry: {name!r}")
    if any(part == ".." for part in parts):
        raise UnsafeArchiveError(f"parent-traversal archive entry: {name!r}")


def _iter_extra_fields(extra: bytes):
    offset = 0
    while offset + 4 <= len(extra):
        header_id = int.from_bytes(extra[offset:offset + 2], "little")
        size = int.from_bytes(extra[offset + 2:offset + 4], "little")
        offset += 4
        if offset + size > len(extra):
            return
        yield header_id, extra[offset:offset + size]
        offset += size


def _reject_link_metadata(info: zipfile.ZipInfo) -> None:
    """Reject hard/symbolic links encoded in Unix extra fields.

    ZIP has no first-class hardlink flag. Info-ZIP stores a link target in the
    PKWARE Unix extra field (0x000d); ASi Unix extra fields (0x756e) carry a
    Unix mode plus optional target name. Reject both rather than letting an
    unusual archive slip through.
    """
    for header_id, data in _iter_extra_fields(info.extra):
        if header_id == 0x000D and len(data) > 12:
            raise UnsafeArchiveError(f"hardlink or linked archive entry: {info.filename!r}")
        if header_id == 0x756E and len(data) >= 6:
            mode = int.from_bytes(data[4:6], "little")
            if stat.S_ISLNK(mode):
                raise UnsafeArchiveError(f"symlink archive entry: {info.filename!r}")
            if len(data) > 14 and stat.S_ISREG(mode):
                raise UnsafeArchiveError(f"hardlink or linked archive entry: {info.filename!r}")


def safe_extract_zip(
    archive: Path,
    out_dir: Path,
    *,
    max_files: int = 20_000,
    max_compressed: int = 500 * 1024 * 1024,
    max_uncompressed: int = 2 * 1024 * 1024 * 1024,
    max_ratio: int = 100,
    max_entry_uncompressed: int | None = None,
) -> Path:
    """Extract an archive safely, rejecting traversal, bombs, links, and encryption."""
    if archive.stat().st_size > max_compressed:
        raise UnsafeArchiveError("compressed archive exceeds the size limit")

    out_dir.mkdir(parents=True, exist_ok=True)
    root = out_dir.resolve()
    entry_limit = max_entry_uncompressed if max_entry_uncompressed is not None else max_uncompressed

    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError("not a valid zip archive") from exc

    with zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise UnsafeArchiveError("archive contains too many entries")

        total_uncompressed = 0
        seen_offsets: dict[int, str] = {}
        for info in infos:
            _reject_unsafe_name(info.filename)
            if info.flag_bits & 0x1:
                raise UnsafeArchiveError(f"encrypted archive entry: {info.filename!r}")
            if info.header_offset in seen_offsets:
                raise UnsafeArchiveError(
                    f"hardlink or duplicate archive entry: {info.filename!r}"
                )
            seen_offsets[info.header_offset] = info.filename
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise UnsafeArchiveError(f"symlink archive entry: {info.filename!r}")
            if stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
                raise UnsafeArchiveError(f"special-file archive entry: {info.filename!r}")
            _reject_link_metadata(info)
            if info.file_size < 0 or info.compress_size < 0:
                raise UnsafeArchiveError(f"invalid size metadata in {info.filename!r}")
            if info.file_size > entry_limit:
                raise UnsafeArchiveError(f"archive entry exceeds the size limit: {info.filename!r}")
            total_uncompressed += info.file_size
            if total_uncompressed > max_uncompressed:
                raise UnsafeArchiveError("uncompressed archive exceeds the size limit")
            if info.file_size > 0:
                if info.compress_size == 0:
                    raise UnsafeArchiveError(f"suspicious compression metadata in {info.filename!r}")
                if info.file_size / info.compress_size > max_ratio:
                    raise UnsafeArchiveError(f"suspicious compression ratio in {info.filename!r}")

        total_written = 0
        for info in infos:
            if info.is_dir():
                continue
            target = (out_dir / info.filename).resolve()
            if not str(target).startswith(str(root) + "/") and target != root:
                raise UnsafeArchiveError(f"archive entry escapes the output directory: {info.filename!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            entry_written = 0
            try:
                with zf.open(info) as src, target.open("wb") as dst:
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        entry_written += len(chunk)
                        total_written += len(chunk)
                        if entry_written > entry_limit:
                            raise UnsafeArchiveError(
                                f"archive entry exceeds the size limit: {info.filename!r}"
                            )
                        if total_written > max_uncompressed:
                            raise UnsafeArchiveError("uncompressed archive exceeds the size limit")
                        dst.write(chunk)
            except BaseException:
                target.unlink(missing_ok=True)
                raise

    return out_dir
