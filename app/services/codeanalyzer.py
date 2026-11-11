"""Code-level cloud-blocker analysis for Gosu, Java, XML, and configuration.

The analyzer is deliberately a *scanner*, not a compiler. It masks comments and
string literals before structural matching, fingerprints secret excerpts instead
of storing them, and never writes to the source snapshot. Every finding points to
a path, line, and excerpt hash so the Architect's patch and the Guardian's
re-scan can be tied back to the same evidence.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.models import CodeFinding, ClaimStrength, Confidence, Severity, StandardFamily
from app.services.parsers.gosu import mask_comments, mask_source, parse_gunit, scan_gosu
from app.services.parsers.product import parse_template_xml
from app.services.redaction import (
    SECRET_KEYS,
    SECRET_PLACEHOLDERS,
    fingerprint,
    is_sensitive_secret_key,
    redact_excerpt,
)
from app.services.textindex import TextIndex

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "codebase_rules.yaml"

DEFAULT_EXCLUDES = {
    ".git", ".venv", "__pycache__", "node_modules", "_gen",
    "generated/gsrc/gw/generated",
}

CODE_SUFFIXES = {
    ".gs", ".java", ".xml", ".yaml", ".yml", ".json", ".sql",
    ".properties", ".gradle", ".kts", ".conf", ".cfg", ".ini",
}

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FINDINGS_PER_RULE_FILE = 40

LOG_CALL = re.compile(
    r"(?i)\b(?:log|logger)\.(?:error|warn|warning|info|debug|trace)\s*\(|"
    r"\bSystem\.(?:out|err)\.print\w*\s*\(|"
    r"(?<!\.)\bprint\s*\("
)
SENSITIVE_LOGGED = re.compile(
    r"(?i)\.(?:get)?(VIN|SSN|password|licence|license|dateOfBirth|apiKey|secret|token)\b"
)
SECRET_PLACEHOLDER_PREFIXES = ("your_", "your-", "replace_", "replace-")
SECRET_EXPRESSION_MARKERS = (" + ", " +", "+ ", "(", ")", "==", "!=")
YAML_SECRET_LINE = re.compile(
    r"(?im)^[ \t]*(?:-[ \t]+)?([A-Za-z_][\w.-]*)[ \t]*:[ \t]*"
    r"([\"']?)([^\n\"'#]+)\2[ \t]*(?:#.*)?$"
)
XML_SECRET_ATTR = re.compile(
    r'(?i)\b([A-Za-z_][\w.:-]*)\s*=\s*(["\'])([^"\']+)\2'
)
XML_SECRET_ELEMENT = re.compile(
    r"(?is)<([A-Za-z_][\w.:-]*)(?:\s[^>]*)?>([^<]+)</\1>"
)


@dataclass
class ScanResult:
    root_label: str
    file_count: int
    files_scanned: int
    loc: int
    findings: list[CodeFinding]
    files: list[dict[str, Any]]
    by_language: dict[str, int]
    by_category: dict[str, int]
    by_severity: dict[str, int]
    score: int
    snapshot_sha: str
    duration_ms: int
    warnings: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    source_texts: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def errors(self) -> int:
        return self.by_severity.get("error", 0)

    @property
    def warnings_count(self) -> int:
        return self.by_severity.get("warning", 0)


def load_code_rules(path: Path | str = RULES_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise ValueError("codebase rule pack is missing a rules list")
    return payload


def _tree_hash(root: Path) -> str:
    pairs: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            data = path.read_bytes()
        except OSError:
            continue
        pairs.append((relative, hashlib.sha256(data).hexdigest()))
    payload = "\n".join(f"{path}:{digest}" for path, digest in pairs).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def classify_file(path: str) -> str:
    lower = path.lower()
    suffix = Path(lower).suffix
    if suffix == ".gs" and ("/gtest/" in lower or lower.startswith("gtest/") or lower.endswith("test.gs")):
        return "gunit"
    if suffix == ".gs":
        return "gosu"
    if suffix == ".java":
        return "java"
    if suffix == ".sql":
        return "sql"
    if suffix == ".properties":
        return "properties"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".xml":
        if "/product/template/" in lower or lower.startswith("product/template/"):
            return "product_template"
        return "xml"
    return "config"


def _languages_for(kind: str) -> set[str]:
    if kind == "gunit":
        return {"gosu", "gunit", "test"}
    if kind == "product_template":
        return {"xml", "product_template"}
    return {kind}


def _is_excluded(relative: str) -> bool:
    normalized = relative.replace("\\", "/").lower()
    for marker in DEFAULT_EXCLUDES:
        if normalized == marker or normalized.startswith(marker + "/") or f"/{marker}/" in normalized:
            return True
    if normalized.startswith("."):
        return True
    return False


def _mask_markup(text: str) -> str:
    """Mask XML/YAML/shell comments without moving line or column positions."""
    def mask_comment(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    masked = re.sub(r"<!--.*?-->", mask_comment, text, flags=re.S)
    lines: list[str] = []
    for line in masked.splitlines(keepends=True):
        if line.lstrip().startswith("#"):
            lines.append("".join("\n" if char == "\n" else " " for char in line))
        else:
            lines.append(line)
    return "".join(lines)


def _line_of(text: str, position: int, index: TextIndex | None = None) -> int:
    return (index or TextIndex(text)).line_at(position)


def _excerpt(text: str, line: int, span: int = 2) -> str:
    return TextIndex(text).excerpt(line, span)


def _fingerprint(rule_id: str, path: str, line: int, excerpt_sha: str) -> str:
    payload = f"{rule_id}|{path}|{line}|{excerpt_sha}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _secret_matches(raw: str, kind: str = "gosu") -> Iterable[tuple[int, str, str, bool]]:
    """Yield ``(position, key, value, placeholder)`` for literal assignments."""
    seen: set[tuple[int, str]] = set()

    def allowed(value: str) -> bool:
        lowered = value.strip().lower()
        return not (
            lowered in SECRET_PLACEHOLDERS
            or re.fullmatch(r"\*+", value.strip()) is not None
            or lowered.startswith(SECRET_PLACEHOLDER_PREFIXES)
            or (value.startswith("<") and value.endswith(">"))
            or value.startswith(("${", "{{"))
            or lowered.startswith(("system.getenv", "getenv", "env."))
        )

    if kind in {"yaml", "properties", "config"}:
        for match in YAML_SECRET_LINE.finditer(raw):
            name, value = match.group(1), match.group(3).strip()
            if not is_sensitive_secret_key(name) or not allowed(value):
                continue
            key = (match.start(), name)
            if key not in seen:
                seen.add(key)
                yield match.start(), name, value, False
        return

    if kind in {"xml", "product_template"}:
        for match in XML_SECRET_ATTR.finditer(raw):
            name, value = match.group(1), match.group(3).strip()
            if is_sensitive_secret_key(name) and allowed(value):
                key = (match.start(), name)
                if key not in seen:
                    seen.add(key)
                    yield match.start(), name, value, False
        for match in XML_SECRET_ELEMENT.finditer(raw):
            name, value = match.group(1).rsplit(":", 1)[-1], match.group(2).strip()
            if is_sensitive_secret_key(name) and allowed(value):
                key = (match.start(), name)
                if key not in seen:
                    seen.add(key)
                    yield match.start(), name, value, False
        return

    code_only = mask_comments(raw)
    values = [match for match in SECRET_KEYS.finditer(code_only)]
    for match in values:
        name = match.group(1)
        if not is_sensitive_secret_key(name):
            continue
        value = match.group(2)
        if not allowed(value):
            continue
        following = code_only[match.end():match.end() + 12].lstrip()
        if following.startswith("+") and not re.search(r"[A-Za-z0-9]{8,}", value):
            continue
        yield match.start(), name, value, False


def _empty_catch_matches(masked: str) -> Iterable[re.Match[str]]:
    for match in re.finditer(r"catch\s*\([^)]*\)\s*\{", masked):
        open_index = masked.find("{", match.end() - 1)
        if open_index == -1:
            continue
        depth = 0
        close_index = -1
        for cursor in range(open_index, len(masked)):
            if masked[cursor] == "{":
                depth += 1
            elif masked[cursor] == "}":
                depth -= 1
                if depth == 0:
                    close_index = cursor
                    break
        if close_index == -1:
            continue
        body = re.sub(r"[\s;]+", "", masked[open_index + 1:close_index])
        if body == "":
            yield match


def _make_finding(*, rule: dict[str, Any], path: str, line: int, column: int,
                  excerpt: str, raw_excerpt: str, method: str,
                  message: str | None = None, redacted: bool = False,
                  index: int = 0) -> CodeFinding:
    clean, detected = redact_excerpt(excerpt)
    if redacted:
        clean, _ = redact_excerpt(raw_excerpt, all_quoted_strings=True)
    excerpt_sha = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    return CodeFinding(
        finding_id=f"CF-{index:04d}",
        rule_id=rule["rule_id"],
        rule_version=str(rule.get("version", "1.0")),
        title=rule["title"],
        category=rule["category"],
        severity=Severity(rule["severity"]),
        claim_strength=ClaimStrength(rule["claim_strength"]),
        standard_family=StandardFamily(rule.get("standard_family", "none")),
        standard_id=rule.get("standard_id"),
        standard_title=rule.get("standard_title"),
        standard_url=rule.get("standard_url"),
        language=method,
        path=path,
        line=max(1, line),
        column=max(1, column),
        excerpt=clean,
        excerpt_sha=excerpt_sha,
        fingerprint=_fingerprint(rule["rule_id"], path, max(1, line), excerpt_sha),
        message=message or rule.get("message", rule["title"]),
        remediation=rule.get("remediation", ""),
        cloud_target=rule.get("cloud_target", ""),
        autofix=rule.get("autofix", "none"),
        confidence=Confidence.PARSED,
        redacted=redacted or detected,
    )


def _apd_overrides(root: Path) -> set[str]:
    """Read codegen nameOverride values already present in a target bundle."""
    overrides: set[str] = set()
    for path in root.rglob("*.yaml"):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        types = payload.get("types") if isinstance(payload, dict) else None
        if not isinstance(types, dict):
            continue
        for value in types.values():
            if isinstance(value, dict):
                for key in ("nameOverride", "name_override", "installedName"):
                    if isinstance(value.get(key), str):
                        overrides.add(value[key])
    return overrides


def analyze_codebase(root: Path | str, *, rules_path: Path | str = RULES_PATH,
                     apd_overrides: Iterable[str] = (),
                     max_files: int = 5000) -> ScanResult:
    """Scan a snapshot and return evidence-bound code findings.

    The source tree is never modified. Symlinks and binary/non-text files are
    listed as skipped rather than silently dropped.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"source root is not a directory: {root}")
    started = time.monotonic()
    pack = load_code_rules(rules_path)
    rules = pack["rules"]
    overrides = set(apd_overrides) | _apd_overrides(root)

    findings: list[CodeFinding] = []
    files: list[dict[str, Any]] = []
    warnings: list[str] = []
    skipped: list[dict[str, str]] = []
    source_texts: dict[str, str] = {}
    by_language: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    loc = 0

    candidates = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    if len(candidates) > max_files:
        warnings.append(f"snapshot has {len(candidates)} files; scanning the first {max_files}")
        candidates = candidates[:max_files]

    for path in candidates:
        relative = path.relative_to(root).as_posix()
        if _is_excluded(relative):
            skipped.append({"path": relative, "reason": "excluded/generated path"})
            continue
        if path.is_symlink():
            skipped.append({"path": relative, "reason": "symlink refused"})
            continue
        suffix = path.suffix.lower()
        if suffix not in CODE_SUFFIXES:
            skipped.append({"path": relative, "reason": f"unsupported suffix {suffix or '(none)'}"})
            continue
        try:
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                skipped.append({"path": relative, "reason": f"{size} bytes exceeds scanner limit"})
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            warnings.append(f"{relative}: cannot read: {exc}")
            skipped.append({"path": relative, "reason": str(exc)})
            continue

        kind = classify_file(relative)
        languages = _languages_for(kind)
        by_language[kind] = by_language.get(kind, 0) + 1
        file_loc = raw.count("\n") + (0 if raw.endswith("\n") or not raw else 1)
        loc += file_loc
        source_texts[relative] = raw
        text_index = TextIndex(raw)
        masked = mask_source(raw) if kind in {"gosu", "java", "gunit"} else _mask_markup(raw)
        per_file: list[str] = []
        per_rule_count: dict[str, int] = {}

        def emit(rule: dict[str, Any], position: int, *, excerpt: str,
                 message: str | None = None, redacted: bool = False,
                 method: str | None = None, always: bool = False) -> None:
            count = per_rule_count.get(rule["rule_id"], 0)
            if count >= MAX_FINDINGS_PER_RULE_FILE:
                return
            per_rule_count[rule["rule_id"]] = count + 1
            line = _line_of(raw, position, text_index)
            column = position - raw.rfind("\n", 0, position)
            finding = _make_finding(
                rule=rule,
                path=relative,
                line=line,
                column=max(1, column),
                excerpt=excerpt,
                raw_excerpt=excerpt,
                method=method or kind,
                message=message,
                redacted=redacted,
                index=len(findings) + 1,
            )
            findings.append(finding)
            per_file.append(finding.finding_id)
            by_category[finding.category] = by_category.get(finding.category, 0) + 1
            by_severity[finding.severity.value] = by_severity.get(finding.severity.value, 0) + 1

        for rule in rules:
            allowed = set(rule.get("languages", []))
            suffixes = rule.get("file_suffixes")
            if allowed and not (languages & allowed):
                continue
            if suffixes and suffix not in {item.lower() for item in suffixes}:
                continue
            detection = rule.get("detection") or {}
            detector = detection.get("kind", "regex_masked")
            if (detector not in {"secret_assignment", "apd_long_type"}
                    and rule["rule_id"] in per_rule_count):
                # One file-level finding is enough for structural rules; the
                # Architect replaces the whole file and the Guardian re-scans it.
                continue

            if detector == "always":
                emit(rule, 0, excerpt=_excerpt(raw, 1), method=kind)
                continue

            if detector == "regex_masked":
                patterns = detection.get("patterns", [])
                hits: list[tuple[int, str]] = []
                for pattern in patterns:
                    try:
                        for match in re.finditer(pattern, masked):
                            hits.append((match.start(), match.group(0)))
                    except re.error as exc:
                        warnings.append(f"{rule['rule_id']}: invalid pattern: {exc}")
                seen_lines: set[int] = set()
                for position, matched in sorted(hits):
                    if detector != "apd_long_type" and len(seen_lines) >= 1:
                        break
                    line = _line_of(raw, position, text_index)
                    if line in seen_lines:
                        continue
                    seen_lines.add(line)
                    emit(rule, position, excerpt=_excerpt(raw, line))
                continue

            if detector == "regex_strings":
                source = mask_comments(raw) if kind in {"gosu", "java", "gunit"} else _mask_markup(raw)
                for pattern in detection.get("patterns", []):
                    try:
                        match = re.search(pattern, source)
                    except re.error as exc:
                        warnings.append(f"{rule['rule_id']}: invalid pattern: {exc}")
                        continue
                    if match:
                        emit(rule, match.start(), excerpt=_excerpt(raw, _line_of(raw, match.start(), text_index)))
                        break
                continue

            if detector == "secret_assignment":
                secret_text = masked if kind in {"xml", "product_template", "yaml", "properties", "config"} else raw
                for position, name, value, _placeholder in _secret_matches(secret_text, kind):
                    line = _line_of(raw, position, text_index)
                    all_values = {
                        match.group(2) for match in SECRET_KEYS.finditer(mask_comments(raw))
                        if match.group(2) and len(match.group(2)) >= 3
                    }
                    redacted, _ = redact_excerpt(
                        _excerpt(raw, line), all_quoted_strings=True,
                        extra_values=all_values,
                    )
                    emit(
                        rule, position, excerpt=redacted, redacted=True,
                        message=(
                            f"Hard-coded value assigned to '{name}' at {relative}:{line}. "
                            f"Value redacted (fingerprint {fingerprint(value)})."
                        ),
                    )
                continue

            if detector == "empty_catch":
                for match in _empty_catch_matches(masked):
                    line = _line_of(raw, match.start(), text_index)
                    emit(rule, match.start(), excerpt=_excerpt(raw, line, span=4), method="lexer")
                continue

            if detector == "commit_in_block":
                if kind not in {"gosu", "gunit"}:
                    continue
                try:
                    doc = scan_gosu(path)
                except Exception as exc:  # pragma: no cover - defensive
                    warnings.append(f"{relative}: cannot parse Gosu blocks: {exc}")
                    continue
                seen: set[int] = set()
                for block in doc.find_blocks("runWithNewBundle"):
                    for commit_line in (block.commit_lines or ([block.commit_line] if block.commit_line else [])):
                        if commit_line in seen:
                            continue
                        seen.add(commit_line)
                        commit_position = 0
                        if 0 < commit_line <= len(text_index.lines):
                            commit_position = sum(
                                len(text_index.lines[i]) + 1 for i in range(commit_line - 1)
                            )
                        emit(
                            rule,
                            commit_position,
                            excerpt=_excerpt(raw, commit_line, span=1),
                            method="lexer",
                            message=f"Explicit commit inside runWithNewBundle at {relative}:{commit_line}.",
                        )
                continue

            if detector == "apd_long_type":
                if kind != "product_template":
                    continue
                limit = int(detection.get("name_limit", 24))
                try:
                    template = parse_template_xml(path)
                except Exception as exc:
                    warnings.append(f"{relative}: cannot parse product template: {exc}")
                    continue
                for type_doc in template.types:
                    if len(type_doc.name) > limit and type_doc.name not in overrides:
                        position = raw.find(type_doc.name)
                        if position < 0:
                            position = 0
                        emit(
                            rule, position,
                            excerpt=type_doc.excerpt,
                            method="xml_xpath",
                            message=(
                                f"APD type '{type_doc.name}' is {len(type_doc.name)} characters. "
                                f"APD truncates product-template type names over {limit} characters "
                                "on import; a codegen nameOverride maps the truncated visualized "
                                "name to the installed name."
                            ),
                        )
                continue

            if detector == "gunit_db":
                if kind != "gunit":
                    continue
                try:
                    test = parse_gunit(path)
                except Exception as exc:
                    warnings.append(f"{relative}: cannot parse GUnit: {exc}")
                    continue
                if test.db_calls:
                    line = next(
                        (i + 1 for i, text in enumerate(text_index.lines)
                         if any(token in text for token in test.db_calls)),
                        1,
                    )
                    emit(
                        rule, max(0, raw.find(test.db_calls[0])),
                        excerpt=_excerpt(raw, line),
                        method="lexer",
                        message=(
                            f"Pure unit test uses database calls ({', '.join(test.db_calls)}) "
                            f"at {relative}:{line}."
                        ),
                    )
                continue

            if detector == "log_pii":
                lines = mask_source(raw).splitlines()
                for cursor, window in enumerate(lines):
                    if not LOG_CALL.search(window):
                        continue
                    if SENSITIVE_LOGGED.search(window):
                        position = sum(len(lines[i]) + 1 for i in range(cursor))
                        emit(rule, position, excerpt=_excerpt(raw, cursor + 1),
                             method="lexer")
                        break
                continue

        files.append({
            "path": relative,
            "kind": kind,
            "loc": file_loc,
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "finding_ids": per_file,
        })

    weighted = (
        by_severity.get("error", 0) * 14
        + by_severity.get("warning", 0) * 5
        + by_severity.get("note", 0) * 1
        + by_severity.get("info", 0) * 1
    )
    score = max(0, min(100, 100 - weighted))
    if by_severity.get("error", 0):
        score = min(score, 68)
    duration_ms = int((time.monotonic() - started) * 1000)
    return ScanResult(
        root_label=root.name,
        file_count=len(candidates),
        files_scanned=len(files),
        loc=loc,
        findings=findings,
        files=files,
        by_language=dict(sorted(by_language.items())),
        by_category=dict(sorted(by_category.items())),
        by_severity=dict(sorted(by_severity.items())),
        score=score,
        snapshot_sha=_tree_hash(root),
        duration_ms=duration_ms,
        warnings=warnings,
        skipped=skipped,
        source_texts=source_texts,
    )


def scan_to_dict(scan: ScanResult) -> dict[str, Any]:
    """Serialize a scan without source text or secret values."""
    return {
        "root_label": scan.root_label,
        "file_count": scan.file_count,
        "files_scanned": scan.files_scanned,
        "loc": scan.loc,
        "findings": [finding.model_dump(mode="json") for finding in scan.findings],
        "files": scan.files,
        "by_language": scan.by_language,
        "by_category": scan.by_category,
        "by_severity": scan.by_severity,
        "score": scan.score,
        "snapshot_sha": scan.snapshot_sha,
        "duration_ms": scan.duration_ms,
        "warnings": scan.warnings,
        "skipped": scan.skipped,
    }
