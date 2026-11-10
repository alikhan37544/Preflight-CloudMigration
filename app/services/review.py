"""Deterministic advisory review engine.

Rules operate on comment/string-masked Gosu or structured XML. Every finding
carries a claim-strength label; heuristics never claim a standard ID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.models import (
    ClaimStrength,
    Confidence,
    Evidence,
    Finding,
    Locator,
    LocatorKind,
    Manifest,
    Severity,
    StandardFamily,
    make_evidence,
)
from app.services.discovery import DiscoveryResult
from app.services.parsers.gosu import mask_comments, mask_source, parse_gunit, scan_gosu
from app.services.parsers.product import parse_template_xml
from app.services.textindex import TextIndex
from app.services.redaction import (
    SECRET_KEYS,
    SECRET_PLACEHOLDERS,
    fingerprint,
    is_sensitive_secret_key,
    redact_excerpt,
)

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "review_rules.yaml"

THEME_RULES = {"PF-GW-LOG-001", "PF-GW-LOG-002"}

SENSITIVE_LOGGED = re.compile(
    r"(?i)\.(?:get)?(VIN|SSN|password|licence|license|dateOfBirth|apiKey|secret|token)\b"
)
LOG_CALL = re.compile(
    r"(?i)\b(?:log|logger)\.(?:error|warn|warning|info|debug|trace)\s*\(|"
    r"\bSystem\.(?:out|err)\.print\w*\s*\(|"
    r"(?<!\.)\bprint\s*\("
)


@dataclass
class ReviewResult:
    findings: list[Finding] = field(default_factory=list)
    readiness: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_rules(path: Path = RULES_PATH) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("rules", [])


class _Evidence:
    def __init__(self) -> None:
        self.items: list[Evidence] = []

    def add(self, *, path: str, line: int, excerpt: str, method: str,
            confidence: Confidence = Confidence.PARSED, redacted: bool = False) -> Evidence:
        clean, detected = redact_excerpt(excerpt)
        ev = make_evidence(
            evidence_id=f"REV-{len(self.items) + 1:04d}",
            path=path,
            locator=Locator(kind=LocatorKind.LINE, value=f"line {line}", line=max(1, line)),
            excerpt=clean,
            method=method,
            confidence=confidence,
            redacted=redacted or detected,
        )
        self.items.append(ev)
        return ev


def _line_at(source: str, position: int, index: TextIndex | None = None) -> int:
    if index is None:
        index = TextIndex(source)
    return index.line_at(position)


def _excerpt_at(source: str, line: int, span: int = 3,
                index: TextIndex | None = None) -> str:
    if index is None:
        index = TextIndex(source)
    return index.excerpt(line, span)


def _match_brace(masked: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _finding(index: int, meta: dict, *, evidence: Evidence, message: str) -> Finding:
    return Finding(
        finding_id=f"F-{index:03d}",
        rule_id=meta["rule_id"],
        rule_version=meta.get("version", "1.0"),
        title=meta["title"],
        severity=Severity(meta["severity"]),
        confidence=Confidence.PARSED,
        claim_strength=ClaimStrength(meta["claim_strength"]),
        standard_family=StandardFamily(meta.get("standard_family", "none")),
        standard_id=meta.get("standard_id"),
        standard_title=meta.get("standard_title"),
        standard_url=meta.get("standard_url"),
        access=meta.get("access", "none"),
        evidence_ids=[evidence.evidence_id],
        message=message,
        remediation=meta.get("remediation", ""),
    )


def run_review(root: Path, manifest: Manifest, discovery: DiscoveryResult,
               *, include_thesis: bool = False) -> ReviewResult:
    rules = {rule["rule_id"]: rule for rule in load_rules()}
    collector = _Evidence()
    findings: list[Finding] = []
    readiness: list[Finding] = []
    warnings: list[str] = []

    def emit(rule_id: str, *, evidence: Evidence, message: str, bucket: list[Finding]) -> None:
        meta = rules[rule_id]
        bucket.append(_finding(len(findings) + len(readiness) + 1, meta, evidence=evidence, message=message))

    for artifact in manifest.artifacts:
        if artifact.status.value not in {"parsed", "partial"}:
            continue
        rel = artifact.path
        path = root / rel
        kind = artifact.kind

        if kind == "gosu":
            try:
                doc = scan_gosu(path)
            except Exception as exc:
                warnings.append(f"{rel}: {exc}")
                continue
            raw, masked = doc.raw, doc.masked
            index = TextIndex(raw)

            for rule_id in ["PF-GW-SQL-001", "PF-GW-PKG-001", "PF-GW-SRV-001"]:
                if rule_id not in rules:
                    continue
                patterns = rules[rule_id]["detection"].get("patterns", [])
                hit = None
                for pattern in patterns:
                    match = re.search(pattern, masked)
                    if match:
                        hit = match
                        break
                if hit:
                    line = _line_at(raw, hit.start(), index)
                    ev = collector.add(path=rel, line=line,
                                       excerpt=_excerpt_at(raw, line, index=index),
                                       method="regex_masked")
                    emit(rule_id, evidence=ev,
                         message=f"{rules[rule_id]['title']} detected at {rel}:{line}.",
                         bucket=findings)

            if "PF-GW-SEC-001" in rules:
                code_only = mask_comments(raw)
                for match in SECRET_KEYS.finditer(code_only):
                    name = match.group(1)
                    if not is_sensitive_secret_key(name):
                        continue
                    value = match.group(2)
                    lowered = value.strip().lower()
                    if lowered in SECRET_PLACEHOLDERS:
                        continue
                    if re.fullmatch(r"\*+", value.strip()):
                        continue
                    if lowered.startswith(("your_", "your-", "replace_", "replace-")):
                        continue
                    if value.startswith("<") and value.endswith(">"):
                        continue
                    if value.startswith("${") or value.startswith("{{"):
                        continue
                    if any(token in value for token in [" + ", " +", "+ ", "(", ")", "==", "!="]):
                        continue
                    following = code_only[match.end():match.end() + 12].lstrip()
                    if following.startswith("+") and not re.search(r"[A-Za-z0-9]{8,}", value):
                        continue
                    value_fingerprint = fingerprint(value)
                    line = _line_at(raw, match.start(), index)
                    all_values = {
                        item.group(2) for item in SECRET_KEYS.finditer(code_only)
                        if item.group(2) and len(item.group(2)) >= 3
                    }
                    excerpt, _ = redact_excerpt(
                        _excerpt_at(raw, line, index=index), all_quoted_strings=True,
                        extra_values=all_values,
                    )
                    ev = collector.add(path=rel, line=line, excerpt=excerpt,
                                       method="regex_masked", redacted=True)
                    emit("PF-GW-SEC-001", evidence=ev,
                         message=(
                             f"Hard-coded value assigned to '{name}' at {rel}:{line}. "
                             f"Value redacted (fingerprint {value_fingerprint})."
                         ), bucket=findings)

            if "PF-GW-EXC-001" in rules:
                for match in re.finditer(r"catch\s*\([^)]*\)\s*\{", masked):
                    open_index = masked.find("{", match.end() - 1)
                    close_index = _match_brace(masked, open_index)
                    if close_index == -1:
                        continue
                    if re.sub(r"[\s;]+", "", masked[open_index + 1:close_index]) == "":
                        line = _line_at(raw, match.start(), index)
                        ev = collector.add(path=rel, line=line,
                                           excerpt=_excerpt_at(raw, line, span=5, index=index),
                                           method="lexer")
                        emit("PF-GW-EXC-001", evidence=ev,
                             message=f"Empty catch block at {rel}:{line}.", bucket=findings)

            if "PF-GW-TX-001" in rules:
                seen_commits: set[int] = set()
                for block in doc.find_blocks("runWithNewBundle"):
                    for commit_line in (block.commit_lines or ([block.commit_line] if block.commit_line else [])):
                        if commit_line in seen_commits:
                            continue
                        seen_commits.add(commit_line)
                        ev = collector.add(
                            path=rel, line=commit_line,
                            excerpt=_excerpt_at(
                                raw, block.start_line,
                                span=max(1, block.end_line - block.start_line + 1),
                                index=index,
                            ),
                            method="lexer",
                        )
                        emit("PF-GW-TX-001", evidence=ev,
                             message=f"Explicit commit inside runWithNewBundle at {rel}:{commit_line}.",
                             bucket=findings)

            if include_thesis and "PF-GW-LOG-001" in rules:
                code_only = mask_source(raw)
                lines = code_only.splitlines()
                line_cursor = 0
                while line_cursor < len(lines):
                    start = line_cursor
                    window = lines[line_cursor]
                    if LOG_CALL.search(window):
                        balance = window.count("(") - window.count(")")
                        while balance > 0 and line_cursor + 1 < len(lines):
                            line_cursor += 1
                            window += "\n" + lines[line_cursor]
                            balance += lines[line_cursor].count("(") - lines[line_cursor].count(")")
                        if SENSITIVE_LOGGED.search(window):
                            line_number = start + 1
                            ev = collector.add(
                                path=rel, line=line_number,
                                excerpt=_excerpt_at(
                                    raw, line_number,
                                    span=min(4, line_cursor - start + 1),
                                    index=index,
                                ),
                                method="lexer",
                            )
                            emit("PF-GW-LOG-001", evidence=ev,
                                 message=f"Sensitive field written to a log at {rel}:{line_number}.",
                                 bucket=findings)
                            break
                    line_cursor += 1

            if include_thesis and "PF-GW-LOG-002" in rules:
                patterns = rules["PF-GW-LOG-002"]["detection"].get("patterns", [])
                for pattern in patterns:
                    match = re.search(pattern, masked)
                    if match:
                        line = _line_at(raw, match.start(), index)
                        ev = collector.add(path=rel, line=line,
                                           excerpt=_excerpt_at(raw, line, index=index),
                                           method="lexer")
                        emit("PF-GW-LOG-002", evidence=ev,
                             message=f"Print or stack-trace output at {rel}:{line}.", bucket=findings)
                        break

        elif kind == "gunit" and "PF-GW-GUNIT-001" in rules:
            try:
                test = parse_gunit(path)
            except Exception as exc:
                warnings.append(f"{rel}: {exc}")
                continue
            if test.db_calls:
                raw = path.read_text(encoding="utf-8", errors="replace")
                index = TextIndex(raw)
                line = next(
                    (i + 1 for i, text in enumerate(index.lines)
                     if any(token in text for token in test.db_calls)),
                    1,
                )
                ev = collector.add(path=rel, line=line,
                                   excerpt=_excerpt_at(raw, line, index=index),
                                   method="lexer")
                emit("PF-GW-GUNIT-001", evidence=ev,
                     message=f"Pure unit test uses database calls ({', '.join(test.db_calls)}) at {rel}:{line}.",
                     bucket=findings)

        elif kind == "template_xml" and "PF-GW-NAM-001" in rules:
            try:
                template = parse_template_xml(path)
            except Exception as exc:
                warnings.append(f"{rel}: {exc}")
                continue
            for type_doc in template.types:
                if len(type_doc.name) > 24:
                    ev = collector.add(path=rel, line=type_doc.line, excerpt=type_doc.excerpt,
                                       method="xml_xpath", confidence=Confidence.LINKED)
                    emit("PF-GW-NAM-001", evidence=ev,
                         message=(
                             f"APD type '{type_doc.name}' is a {len(type_doc.name)}-character "
                             "product-template type. APD truncates type names over 24 characters "
                             "on import, so endpoint generation fails to compile. A codegen "
                             "nameOverride maps the truncated visualized name to the installed "
                             "name. Synthetic fixture type."
                         ), bucket=findings)

        elif kind == "product_xml" and "PF-GW-SBT-001" in rules:
            raw = path.read_text(encoding="utf-8", errors="replace")
            index = TextIndex(raw)
            sbt_element = None
            try:
                from app.services.parsers._xml import safe_parser
                from lxml import etree

                tree = etree.parse(str(path), safe_parser())
                for element in tree.getroot().iter():
                    if not isinstance(element.tag, str):
                        continue
                    value = (element.get("standardsBasedTemplate") or "").strip().lower()
                    if value == "true":
                        sbt_element = (element, int(element.sourceline or 1))
                        break
            except Exception:
                sbt_element = None
            if sbt_element is not None:
                _element, line = sbt_element
                ev = collector.add(path=rel, line=line,
                                   excerpt=_excerpt_at(raw, line, index=index),
                                   method="xml_xpath", confidence=Confidence.LINKED)
                meta = rules["PF-GW-SBT-001"]
                readiness.append(
                    _finding(len(findings) + 1, meta, evidence=ev,
                             message=(
                                 f"Synthetic marker heuristic: {rel} contains "
                                 "standardsBasedTemplate=\"true\". This is not an official SBT "
                                 "assessment or a conversion check; the documented Olos SBT "
                                 "limitation is context for reviewer follow-up on the target release."
                             ))
                )

    return ReviewResult(
        findings=findings,
        readiness=readiness,
        evidence=collector.items,
        warnings=warnings,
    )
