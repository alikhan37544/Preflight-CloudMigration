"""Snapshot intake, hashing, classification, and archive safety.

The source snapshot is always treated as read-only. Intake never writes under
the snapshot root; callers can verify immutability with snapshot_hash().
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
import zlib
from pathlib import Path

from lxml import etree

from app.models import Artifact, ArtifactStatus, Manifest
from app.services.parsers.config import parse_config_yaml
from app.services.redaction import redact_excerpt

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

MAX_ARCHIVE_PATH_CHARS = 1024
MAX_ARCHIVE_PATH_PARTS = 64


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


def _marker_sha256(*parts: str) -> str:
    """Deterministic digest for entries whose content cannot or must not be read."""
    return _sha256_bytes("\x00".join(parts).encode("utf-8"))


def _display_text(value: str) -> str:
    """Return a JSON-safe display string for a filesystem path or target.

    Linux paths are bytes. Python decodes undecodable bytes with surrogate
    escapes, which cannot be serialized as UTF-8 JSON. Escaping only those
    bytes keeps normal paths unchanged while making the display path stable.
    """
    return os.fsencode(value).decode("utf-8", "backslashreplace")


def _safe_warning(text: str) -> str:
    """Remove secret-looking values from parser error text before persisting it."""
    return redact_excerpt(text)[0]


def _special_kind(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return "special"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "char_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    return "special"


def _scan_entries(root: Path) -> list[tuple[Path, str, str, str | None]]:
    """Walk without following links and without hiding unreadable entries.

    Returns ``(real_path, relative_path, category, detail)`` tuples. Categories
    are ``file``, ``symlink``, ``special``, ``unreadable`` (entry metadata
    could not be read), and ``unreadable_dir`` (directory could not be listed).
    Normal directories are traversal nodes, not entries.
    """
    results: list[tuple[Path, str, str, str | None]] = []
    pending: list[tuple[Path, str]] = [(Path(root), "")]
    while pending:
        directory, prefix = pending.pop()
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda entry: os.fsencode(entry.name))
        except OSError as exc:
            results.append((Path(directory), prefix or ".", "unreadable_dir",
                            type(exc).__name__))
            continue
        child_dirs: list[tuple[Path, str]] = []
        for entry in entries:
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            path = Path(entry.path)
            try:
                if entry.is_symlink():
                    results.append((path, rel, "symlink", None))
                elif entry.is_dir(follow_symlinks=False):
                    child_dirs.append((path, rel))
                elif entry.is_file(follow_symlinks=False):
                    results.append((path, rel, "file", None))
                else:
                    results.append((path, rel, "special", _special_kind(path)))
            except OSError as exc:
                results.append((path, rel, "unreadable", type(exc).__name__))
        # Reverse for LIFO traversal; the final sort makes ordering explicit.
        pending.extend(reversed(child_dirs))
    results.sort(key=lambda item: item[1])
    return results


def snapshot_hash(root: Path) -> str:
    """SHA-256 over sorted path/content entries.

    Regular files contribute ``(relative_path, file_sha256)``. Symlinks
    contribute ``(relative_path, "symlink", target, mode)`` so retargeting a
    link changes the hash without reading the target. Unreadable and special
    entries contribute an explicit marker instead of being dropped. Modification
    times are deliberately excluded so repeated runs are reproducible across
    copies.
    """
    entries: list[list] = []
    for path, rel, category, detail in _scan_entries(root):
        display = _display_text(rel)
        if category == "symlink":
            # Symlinks are listed as unsupported artifacts. Hash the link
            # itself (path, target, mode) so retargeting changes the snapshot
            # hash without following the target.
            try:
                target = os.readlink(path)
            except OSError:
                target = ""
            try:
                mode = path.lstat().st_mode & 0o7777
            except OSError:
                mode = 0
            entries.append([display, "symlink", _display_text(target), mode])
        elif category == "file":
            try:
                data = path.read_bytes()
            except OSError as exc:
                entries.append([display, "unreadable", type(exc).__name__])
            else:
                entries.append([display, _sha256_bytes(data)])
        elif category == "unreadable_dir":
            entries.append([display, "unreadable_directory", detail or "OSError"])
        elif category == "special":
            entries.append([display, "special", detail or "special"])
        else:
            entries.append([display, "unreadable", detail or "OSError"])
    payload = json.dumps(entries, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_manifest(root: Path, *, snapshot_id: str, project_id: str) -> Manifest:
    if not root.is_dir():
        raise FileNotFoundError(root)

    artifacts: list[Artifact] = []
    unsupported: list[str] = []
    total_size = 0
    warnings: list[str] = []

    for path, rel, category, detail in _scan_entries(root):
        display = _display_text(rel)
        if category == "symlink":
            # Never follow links, but never hide them either: they are listed
            # as explicit unsupported artifacts with a warning.
            try:
                target = os.readlink(path)
            except OSError:
                target = ""
            target_bytes = target.encode("utf-8", "surrogateescape")
            artifacts.append(
                Artifact(
                    path=display,
                    sha256=_sha256_bytes(target_bytes),
                    size=len(target_bytes),
                    kind="symlink",
                    parser="none",
                    status=ArtifactStatus.UNSUPPORTED,
                    warnings=[_safe_warning("symlink entries are not followed")],
                    line_count=0,
                )
            )
            total_size += len(target_bytes)
            unsupported.append(display)
            warnings.append(_safe_warning(f"{display}: symlink not followed"))
            continue
        if category == "unreadable_dir":
            reason = f"unreadable: {detail or 'OSError'}"
            artifacts.append(
                Artifact(
                    path=display,
                    sha256=_marker_sha256(display, "unreadable_directory", reason),
                    size=0,
                    kind="directory",
                    parser="none",
                    status=ArtifactStatus.UNSUPPORTED,
                    warnings=[_safe_warning(
                        f"{reason}; directory contents cannot be listed"
                    )],
                    line_count=0,
                )
            )
            unsupported.append(display)
            warnings.append(_safe_warning(
                f"{display}: {reason}; directory contents cannot be listed"
            ))
            continue
        if category == "special":
            kind = detail or "special"
            reason = f"special file type: {kind}; not read"
            artifacts.append(
                Artifact(
                    path=display,
                    sha256=_marker_sha256(display, "special", kind),
                    size=0,
                    kind=kind,
                    parser="none",
                    status=ArtifactStatus.UNSUPPORTED,
                    warnings=[_safe_warning(reason)],
                    line_count=0,
                )
            )
            unsupported.append(display)
            warnings.append(_safe_warning(f"{display}: {reason}"))
            continue
        if category == "unreadable":
            reason = f"unreadable: {detail or 'OSError'}"
            artifacts.append(
                Artifact(
                    path=display,
                    sha256=_marker_sha256(display, "unreadable", reason),
                    size=0,
                    kind="unreadable",
                    parser="none",
                    status=ArtifactStatus.UNSUPPORTED,
                    warnings=[_safe_warning(reason)],
                    line_count=0,
                )
            )
            unsupported.append(display)
            warnings.append(_safe_warning(f"{display}: {reason}"))
            continue

        try:
            data = path.read_bytes()
        except OSError as exc:
            reason = f"unreadable: {type(exc).__name__}"
            artifacts.append(
                Artifact(
                    path=display,
                    sha256=_marker_sha256(display, "unreadable", reason),
                    size=0,
                    kind="unreadable",
                    parser="none",
                    status=ArtifactStatus.UNSUPPORTED,
                    warnings=[_safe_warning(reason)],
                    line_count=0,
                )
            )
            unsupported.append(display)
            warnings.append(_safe_warning(f"{display}: {reason}"))
            continue
        total_size += len(data)
        kind, parser = _kind_for(display)
        status = ArtifactStatus.PARSED
        item_warnings: list[str] = []
        corrupt_label: str | None = None
        line_count = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)

        if kind == "binary" or _looks_binary(data):
            status = ArtifactStatus.BINARY
            if kind is None:
                kind = "binary"
            unsupported.append(display)
        elif kind is None:
            status = ArtifactStatus.UNSUPPORTED
            kind = "unknown"
            parser = None
            unsupported.append(display)
        elif parser in {"xml", "pcf", "entity", "typelist"} or display.lower().endswith(tuple(XML_SUFFIXES)):
            try:
                etree.fromstring(data, _safe_xml_parser())
            except etree.XMLSyntaxError as exc:
                status = ArtifactStatus.CORRUPT
                item_warnings.append(_safe_warning(f"XML parse error: {exc}"))
                corrupt_label = "XML"
                unsupported.append(display)
            except ValueError as exc:  # e.g. encoding declaration problems
                status = ArtifactStatus.CORRUPT
                item_warnings.append(_safe_warning(f"XML parse error: {exc}"))
                corrupt_label = "XML"
                unsupported.append(display)
        elif parser == "json":
            try:
                json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                status = ArtifactStatus.CORRUPT
                item_warnings.append(_safe_warning(f"JSON parse error: {exc}"))
                corrupt_label = "JSON"
                unsupported.append(display)
        elif parser == "config":
            try:
                parse_config_yaml(path)
            except Exception as exc:  # malformed or tagged YAML must not abort intake
                status = ArtifactStatus.CORRUPT
                item_warnings.append(_safe_warning(f"YAML parse error: {exc}"))
                corrupt_label = "YAML"
                unsupported.append(display)

        if status is ArtifactStatus.CORRUPT:
            warnings.append(_safe_warning(f"{display}: corrupt {corrupt_label or 'file'}"))

        artifacts.append(
            Artifact(
                path=display,
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
    if len(normalised) > MAX_ARCHIVE_PATH_CHARS:
        raise UnsafeArchiveError(
            f"archive entry path exceeds {MAX_ARCHIVE_PATH_CHARS} characters: {name!r}"
        )
    trimmed = normalised.rstrip("/")
    parts = trimmed.split("/") if trimmed else []
    if not parts:
        raise UnsafeArchiveError(f"empty archive entry: {name!r}")
    if len(parts) > MAX_ARCHIVE_PATH_PARTS:
        raise UnsafeArchiveError(
            f"archive entry exceeds {MAX_ARCHIVE_PATH_PARTS} path components: {name!r}"
        )
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
            seen_names: set[str] = set()
            for info in infos:
                _reject_unsafe_name(info.filename)
                if info.flag_bits & 0x1:
                    raise UnsafeArchiveError(f"encrypted archive entry: {info.filename!r}")
                normalised = info.filename.rstrip("/")
                if normalised in seen_names:
                    raise UnsafeArchiveError(
                        f"duplicate archive entry name: {info.filename!r}"
                    )
                seen_names.add(normalised)
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
                try:
                    target = (out_dir / info.filename).resolve()
                    if not str(target).startswith(str(root) + "/") and target != root:
                        raise UnsafeArchiveError(
                            f"archive entry escapes the output directory: {info.filename!r}"
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    entry_written = 0
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
                except OSError as exc:
                    raise UnsafeArchiveError(
                        f"archive entry could not be extracted: {info.filename!r}: "
                        f"{type(exc).__name__}"
                    ) from exc
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        # Corrupt compressed data or a CRC mismatch is an archive error, not a
        # 500. Clean up partial files and report it through the intake contract.
        shutil.rmtree(out_dir, ignore_errors=True)
        raise UnsafeArchiveError(
            f"archive is corrupt or truncated: {type(exc).__name__}: {exc}"
        ) from exc
    except BaseException:
        # Never leave a partially extracted snapshot behind, even when the
        # filesystem (not our validators) raises the error.
        shutil.rmtree(out_dir, ignore_errors=True)
        raise

    return out_dir
