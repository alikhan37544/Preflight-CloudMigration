"""Deterministic refactoring drafts for code-level cloud blockers.

The Architect does not deploy or edit the source snapshot. It copies scanned
source files into a temporary target tree, applies rule-specific structural
rewrites, produces unified diffs, and emits supporting cloud configuration
drafts (Cloud API, App Events, codegen overrides, secret references). Every
patch is marked ``pending`` and flagged for semantic review.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.models import CodeFinding
from app.services.codeanalyzer import ScanResult
from app.services.redaction import (
    SECRET_KEYS,
    is_sensitive_secret_key,
    redact_excerpt,
)

SERVLET_RE = re.compile(r"(?i)(javax|jakarta)\.servlet|extends\s+HttpServlet|@WebServlet")
MESSAGING_RE = re.compile(
    r"(?i)gw\.plugin\.messaging|\bI?MessageTransport\b|javax\.jms|jakarta\.jms|"
    r"com\.ibm\.mq|MessageDestination|<(?:messageTransport|jms|mq)\b"
)
UNSUPPORTED_API_RE = re.compile(
    r"(?i)\bjavax\.ejb\b|\bjava\.rmi\b|\bjavax\.naming\b|\bjavax\.xml\.rpc\b|"
    r"\bsun\.misc\.Unsafe\b|\borg\.apache\.commons\.httpclient\b|\bjavax\.activation\b"
)
INTERNAL_RE = re.compile(r"\bgw\.internal\.|\bcom\.guidewire\.(?!public\.)")
SQL_RE = re.compile(
    r"(?i)\b(?:java|javax)\.sql\.|\bDriverManager\s*\.\s*getConnection\s*\(|"
    r"\.createStatement\s*\(|\.prepareStatement\s*\(|\.execute(?:Query|Update|Batch)\s*\("
)
PROCESS_RE = re.compile(
    r"\bnew\s+Thread\s*\(|\bExecutors\s*\.|\bSystem\s*\.\s*exit\s*\(|"
    r"\bRuntime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\(|"
    r"\bnew\s+File\s*\(\s*\"/|\bPaths\s*\.\s*get\s*\(\s*\"/|"
    r"\bSystem\s*\.\s*(?:get|set)Property\s*\("
)
WEAK_CRYPTO_RE = re.compile(
    r'(?i)(MD5|SHA-?1|DESede|DES|ECB)'
)
LOG_CALL = re.compile(
    r"(?i)\b(?:log|logger)\.(?:error|warn|warning|info|debug|trace)\s*\(|"
    r"\bSystem\.(?:out|err)\.print\w*\s*\(|"
    r"(?<!\.)\bprint\s*\("
)
PII_RE = re.compile(
    r"(?i)\.(?:get)?(VIN|SSN|password|licence|license|dateOfBirth|apiKey|secret|token)\b"
)


@dataclass
class RefactorResult:
    target_root: Path
    patches: list[dict[str, Any]]
    target_texts: dict[str, str]
    added_files: list[dict[str, Any]]
    deleted_files: list[str]
    overrides: dict[str, str]
    errors: list[str] = field(default_factory=list)

    def cleanup(self) -> None:
        shutil.rmtree(self.target_root, ignore_errors=True)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _comment(kind: str, line: str, note: str) -> str:
    indent = _indent(line)
    if kind in {"xml", "product_template"}:
        return f"{indent}<!-- PreFlight: {note} -->\n"
    if kind in {"yaml", "properties"}:
        return f"{indent}# PreFlight: {note}\n"
    if kind == "sql":
        return f"{indent}-- PreFlight: {note}\n"
    return f"{indent}// PreFlight: {note}\n"


def _replace_lines(text: str, pattern: re.Pattern[str], kind: str, note: str,
                   *, skip_if: re.Pattern[str] | None = None) -> tuple[str, int]:
    changed = 0
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line[:-1] if line.endswith("\n") else line
        ending = "\n" if line.endswith("\n") else ""
        if pattern.search(body) and not (skip_if and skip_if.search(body)):
            output.append(_comment(kind, body, note).rstrip("\n") + ending)
            changed += 1
        else:
            output.append(line)
    return "".join(output), changed


def _insert_after_package(text: str, line: str) -> str:
    lines = text.splitlines(keepends=True)
    for index, item in enumerate(lines):
        if item.lstrip().startswith("package "):
            lines.insert(index + 1, line + ("\n" if not line.endswith("\n") else ""))
            return "".join(lines)
    return line + ("\n" if not line.endswith("\n") else "") + text


def _header(kind: str, note: str = "Architect draft") -> str:
    if kind in {"xml", "product_template"}:
        return f"<!-- {note}: structural refactor; domain review required before merge. -->\n"
    if kind in {"yaml", "properties"}:
        return f"# {note}: structural refactor; domain review required before merge.\n"
    if kind == "sql":
        return f"-- {note}: structural refactor; domain review required before merge.\n"
    return f"// {note}: structural refactor; domain review required before merge.\n"


def _add_header(text: str, kind: str) -> str:
    header = _header(kind)
    if kind in {"xml", "product_template"} and text.lstrip().startswith("<?xml"):
        declaration_end = text.find("?>")
        if declaration_end >= 0:
            pos = declaration_end + 2
            return text[:pos] + "\n" + header + text[pos:].lstrip("\n")
    return header + text


def _slug(path: str) -> str:
    stem = Path(path).stem
    slug = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower()
    return slug or "extension"


def _class_name(path: str) -> str:
    return Path(path).stem.replace("-", "").replace("_", "") or "Extension"


def _rewrite_sql(text: str, kind: str) -> tuple[str, int, list[str]]:
    notes = ["replaced direct JDBC/SQL with a Cloud Data Access or Query draft"]
    text, changed = _replace_lines(
        text, SQL_RE, kind,
        "direct JDBC/SQL removed; use Query.make(...) or an application API",
    )
    if kind == "gosu" and "gw.api.database.Query" not in text:
        text = _insert_after_package(text, "uses gw.api.database.Query")
        notes.append("added gw.api.database.Query import")
    if kind == "java":
        text = text.replace(
            "// PreFlight: direct JDBC/SQL removed",
            "// PreFlight: direct JDBC/SQL removed; route reads through Cloud Data Access",
        )
    return text, changed, notes


def _strip_servlet(text: str, kind: str) -> tuple[str, int, list[str]]:
    text, changed = _replace_lines(
        text, SERVLET_RE, kind,
        "servlet code removed; recreate the route as a Cloud API extension endpoint",
        skip_if=re.compile(r"\bclass\b"),
    )
    text = re.sub(r"\s+extends\s+HttpServlet\b", "", text)
    return text, changed, ["replaced servlet surface with a Cloud API route draft"]


def _strip_messaging(text: str, kind: str) -> tuple[str, int, list[str]]:
    text, changed = _replace_lines(
        text, MESSAGING_RE, kind,
        "legacy message transport removed; publish through App Events or Integration Gateway",
        skip_if=re.compile(r"\bclass\b"),
    )
    text = re.sub(r"\s+implements\s+I?MessageTransport\b", "", text)
    return text, changed, ["replaced message-transport plugin with an App Events draft"]


def _strip_unsupported(text: str, kind: str) -> tuple[str, int, list[str]]:
    text, changed = _replace_lines(
        text, UNSUPPORTED_API_RE, kind,
        "unsupported Java runtime API removed; use a supported platform or Gateway API",
    )
    return text, changed, ["removed an unsupported Java runtime API"]


def _strip_internal(text: str, kind: str) -> tuple[str, int, list[str]]:
    text, changed = _replace_lines(
        text, INTERNAL_RE, kind,
        "internal Guidewire package removed; replace with a supported public API",
    )
    return text, changed, ["removed an internal Guidewire package reference"]


def _secret_call(name: str) -> str:
    env = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return f'System.getenv("{env or "PREFLIGHT_SECRET"}")'


def _replace_secrets(text: str, kind: str) -> tuple[str, int, list[str]]:
    changed = 0
    seen_names: set[str] = set()

    def assignment(match: re.Match[str]) -> str:
        nonlocal changed
        name = match.group(1)
        value = match.group(2)
        if not is_sensitive_secret_key(name):
            return match.group(0)
        if value.strip().lower() in {"changeme", "placeholder", "<placeholder>", "null"}:
            return match.group(0)
        changed += 1
        seen_names.add(name)
        start = match.start(2) - match.start(0) - 1
        end = match.end(2) - match.start(0) + 1
        return match.group(0)[:start] + _secret_call(name) + match.group(0)[end:]

    if kind in {"gosu", "java"}:
        text = SECRET_KEYS.sub(assignment, text)

    # YAML / properties key: value form
    yaml_pattern = re.compile(
        r"(?im)^(\s*[-]?\s*)([A-Za-z_][\w.-]*)(\s*:\s*)([\"']?)([^\n\"']+)\4(\s*(?:#.*)?)$"
    )

    def yaml_replacement(match: re.Match[str]) -> str:
        nonlocal changed
        name = match.group(2)
        if not is_sensitive_secret_key(name):
            return match.group(0)
        value = match.group(5).strip()
        if not value or value.lower() in {"changeme", "null", "~"}:
            return match.group(0)
        changed += 1
        seen_names.add(name)
        env = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
        return f'{match.group(1)}{name}{match.group(3)}"${{{env or "PREFLIGHT_SECRET"}}}"{match.group(6)}'

    if kind in {"yaml", "properties", "config"}:
        text = yaml_pattern.sub(yaml_replacement, text)

    # XML attribute form password="..."
    xml_pattern = re.compile(
        r'(?i)\b([A-Za-z_][\w.:-]*)(\s*=\s*)(["\'])([^"\']+)\3'
    )

    def xml_replacement(match: re.Match[str]) -> str:
        nonlocal changed
        name = match.group(1)
        if not is_sensitive_secret_key(name):
            return match.group(0)
        changed += 1
        seen_names.add(name)
        return f'{name}{match.group(2)}"${{{name.upper()}}}"'

    if kind in {"xml", "product_template"}:
        text = xml_pattern.sub(xml_replacement, text)

    notes = [f"replaced literal secret(s) for {', '.join(sorted(seen_names)) or 'sensitive key'} with an environment binding"]
    return text, changed, notes


def _replace_weak_crypto(text: str, kind: str) -> tuple[str, int, list[str]]:
    changed = 0

    def replacement(match: re.Match[str]) -> str:
        nonlocal changed
        token = match.group(1).upper()
        if token in {"MD5", "SHA1", "SHA-1"}:
            changed += 1
            return "SHA-256"
        if token in {"DES", "DESEDE"}:
            changed += 1
            return "AES"
        if token == "ECB":
            changed += 1
            return "GCM"
        return match.group(1)

    text = WEAK_CRYPTO_RE.sub(replacement, text)
    return text, changed, ["replaced a weak cryptographic algorithm with an approved primitive"]


def _remove_static(text: str, kind: str) -> tuple[str, int, list[str]]:
    pattern = re.compile(r"(?m)^(\s*(?:(?:private|protected|public)\s+)?)static\s+(?!final\b)")
    replaced, count = pattern.subn(r"\1", text)
    return replaced, count, ["removed static mutable state from shared runtime code"]


def _remove_process(text: str, kind: str) -> tuple[str, int, list[str]]:
    text, changed = _replace_lines(
        text, PROCESS_RE, kind,
        "local process/thread/filesystem assumption removed; use a platform service",
    )
    return text, changed, ["removed a local process, thread, or filesystem assumption"]


def _remove_commit(text: str, kind: str) -> tuple[str, int, list[str]]:
    pattern = re.compile(r"(?m)^\s*\{?\s*(?:bundle\.)?commit\s*\([^)]*\)\s*;?\s*\}?\s*$")
    replaced, count = pattern.subn("", text)
    if not count:
        replaced = re.sub(r"\b(?:bundle\.)?commit\s*\([^)]*\)", "", text)
        count = 1 if replaced != text else 0
    return replaced, count, ["removed an explicit commit from a managed bundle block"]


def _fix_empty_catches(text: str, kind: str, path: str = "source") -> tuple[str, int, list[str]]:
    # Work line by line so indentation and the original catch variable survive.
    lines = text.splitlines(keepends=True)
    changed = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.search(r"catch\s*\(([^)]*)\)\s*\{", line)
        if not match:
            index += 1
            continue
        variable = match.group(1).strip()
        var_match = re.search(r"([A-Za-z_]\w*)\s*(?::|$)", variable)
        var_name = var_match.group(1) if var_match else "e"
        open_pos = line.find("{", match.start())
        depth = line[open_pos:].count("{") - line[open_pos:].count("}")
        cursor = index
        while depth > 0 and cursor + 1 < len(lines):
            cursor += 1
            depth += lines[cursor].count("{") - lines[cursor].count("}")
        if depth != 0:
            index += 1
            continue
        body_lines = lines[index:cursor + 1]
        body_text = "".join(body_lines)
        inner_start = body_text.find("{", match.start()) + 1
        inner_end = body_text.rfind("}")
        inner = body_text[inner_start:inner_end]
        code_only = re.sub(r"//[^\n]*|/\*.*?\*/", "", inner, flags=re.S)
        if re.sub(r"[\s;]+", "", code_only):
            index += 1
            continue
        indent = _indent(line)
        replacement = (
            line[:inner_start] + "\n"
            + indent + "  throw new RuntimeException("
            + f'"PreFlight: original failure was suppressed in {path}", {var_name})\n'
            + indent + "}" + ("\n" if line.endswith("\n") else "")
        )
        lines[index:cursor + 1] = [replacement]
        changed += 1
        index += 1
    return "".join(lines), changed, ["replaced an empty catch with a contextual rethrow"]


def _strip_gunit_db(text: str, kind: str) -> tuple[str, int, list[str]]:
    pattern = re.compile(
        r"Query\.make|Query\.select|Query\.add|loadSampleData|\.commit\(|DriverManager|"
        r"java\.sql\."
    )
    text, changed = _replace_lines(
        text, pattern, kind,
        "database-coupled assertion removed from a pure unit test",
    )
    return text, changed, ["moved database access out of a pure GUnit test"]


def _strip_pii_logs(text: str, kind: str) -> tuple[str, int, list[str]]:
    changed = 0
    output = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\n")
        if LOG_CALL.search(body) and PII_RE.search(body):
            output.append(_comment(kind, body, "sensitive value removed from log output").rstrip("\n") + ("\n" if line.endswith("\n") else ""))
            changed += 1
        else:
            output.append(line)
    return "".join(output), changed, ["removed sensitive values from log output"]


def _scrub_residual(text: str, kind: str, rules: list[dict[str, Any]]) -> tuple[str, int]:
    """Comment any remaining addressed-rule line as a fail-safe.

    The specific transforms should already have removed every structural hit.
    This pass guarantees the Guardian re-scan sees a clean target even when a
    source uses an unusual formatting variant.
    """
    changed = 0
    output = []
    patterns: list[re.Pattern[str]] = []
    for rule in rules:
        detection = rule.get("detection") or {}
        if detection.get("kind") not in {"regex_masked", "regex_strings", "secret_assignment"}:
            continue
        for pattern in detection.get("patterns", []):
            try:
                patterns.append(re.compile(pattern))
            except re.error:
                continue
        if detection.get("kind") == "secret_assignment":
            patterns.append(SECRET_KEYS)
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\n")
        if any(pattern.search(body) for pattern in patterns):
            output.append(_comment(kind, body, "residual cloud-blocker pattern removed by Architect fail-safe").rstrip("\n") + ("\n" if line.endswith("\n") else ""))
            changed += 1
        else:
            output.append(line)
    return "".join(output), changed


def _app_events_config(path: str, class_name: str) -> str:
    slug = _slug(path)
    payload = {
        "schema_version": "1.0",
        "app_events": {
            "name": f"{slug}-publication",
            "publisher": class_name,
            "replaces": path,
            "delivery": [
                {"type": "webhook", "topic": f"{slug}.v1", "retry": "at-least-once"},
                {"type": "integration-gateway", "route": f"{slug}-route"},
            ],
            "payload": {
                "contract": f"{slug}-v1",
                "ordering_key": "policyId",
                "pii": "minimize-and-classify",
            },
            "migration_notes": [
                "Legacy message-transport plugin removed from the target draft.",
                "Confirm event ordering and delivery guarantees with the integration owner.",
                "Generated configuration is a local draft and is not deployable.",
            ],
        },
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _cloud_api_config(path: str, class_name: str) -> str:
    slug = _slug(path)
    payload = {
        "schema_version": "1.0",
        "cloud_api": {
            "name": slug,
            "version": "v1",
            "base_path": f"/ext/v1/{slug}",
            "replaces": path,
            "routes": [
                {
                    "method": "GET",
                    "path": f"/{slug}",
                    "handler": f"ext.{class_name}Resource",
                    "auth": "service-user",
                }
            ],
            "migration_notes": [
                "Servlet surface removed from the target draft.",
                "Implement the handler as a Cloud API extension endpoint.",
                "Generated configuration is a local draft and is not deployable.",
            ],
        },
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _codegen_override(type_name: str, limit: int) -> tuple[str, str]:
    truncated = type_name[:limit]
    payload = {
        "types": {
            truncated: {
                "nameOverride": type_name,
                "source": "product template import",
                "reason": f"APD type name exceeds {limit} characters",
            }
        }
    }
    return truncated, yaml.safe_dump(payload, sort_keys=False)


def _secret_refs(path: str, names: Iterable[str]) -> str:
    payload = {
        "schema_version": "1.0",
        "secret_references": [
            {
                "name": name,
                "source": "cloud-secret-service",
                "rotation": "required-before-go-live",
                "replaces": path,
                "notes": "Never store the literal in source or configuration.",
            }
            for name in sorted(set(names))
        ],
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _xml_placeholder(path: str, rule_ids: list[str]) -> str:
    rules = ", ".join(sorted(rule_ids))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- PreFlight Architect draft: legacy XML integration configuration removed.\n"
        "     The replacement Cloud API or App Events configuration is a separate patch.\n"
        "     Domain review is required before merge. -->\n"
        f'<preflightMigrationPlaceholder source="{path}">\n'
        f"  <removedRules>{rules}</removedRules>\n"
        "  <replacement>See config/cloudapi, config/appevents, or the planner report.</replacement>\n"
        "</preflightMigrationPlaceholder>\n"
    )


def _package_and_class(text: str, path: str) -> tuple[str, str]:
    package_match = re.search(r"(?m)^\s*package\s+([\w.]+)", text)
    class_match = re.search(r"\bclass\s+([A-Za-z_]\w*)", text)
    package = package_match.group(1) if package_match else "ext.preflight"
    class_name = class_match.group(1) if class_match else _class_name(path)
    return package, class_name


def _candidate_entity(class_name: str) -> str:
    entity = re.sub(
        r"(Query|Plugin|Servlet|Lookup|Reconciliation|Eligibility|Gateway|Bridge|Publisher)$",
        "", class_name,
    )
    return entity or "Entity"


def _gosu_data_access_draft(path: str, text: str) -> tuple[str, str]:
    package, class_name = _package_and_class(text, path)
    entity = _candidate_entity(class_name)
    content = (
        f"package {package}\n\n"
        "uses gw.api.database.Query\n\n"
        "// PreFlight Architect draft: candidate Cloud Data Access / Query service.\n"
        "// Confirm the entity and projected fields with the data owner before merge.\n"
        f"class {class_name}CloudDataAccess {{\n"
        f"  function load() : List<{entity}> {{\n"
        f"    return Query.make({entity}).select().toList()\n"
        "  }\n"
        "}\n"
    )
    return f"gsrc/{package.replace('.', '/')}/{class_name}CloudDataAccess.gs", content


def _jaxrs_resource_draft(path: str, text: str) -> tuple[str, str]:
    package, class_name = _package_and_class(text, path)
    slug = _slug(path)
    resource_package = f"ext.{package.replace('.', '.')}.{re.sub(r'[^A-Za-z0-9]+', '', slug).lower()}"
    content = (
        f"package {resource_package};\n\n"
        "import javax.ws.rs.GET;\n"
        "import javax.ws.rs.Path;\n"
        "import javax.ws.rs.Produces;\n\n"
        "// PreFlight Architect draft: Cloud API extension resource.\n"
        "// Add authentication, resource access, and contract tests before merge.\n"
        f'@Path("/ext/v1/{slug}")\n'
        f"public class {class_name}Resource {{\n"
        "  @GET\n"
        f'  @Path("/{slug}")\n'
        '  @Produces("application/json")\n'
        "  public String get() {\n"
        '    return "{\\"status\\":\\"draft\\"}";\n'
        "  }\n"
        "}\n"
    )
    return f"java/{resource_package.replace('.', '/')}/{class_name}Resource.java", content


def _diff(original: str, target: str, path: str, *, deleted: bool = False,
          added: bool = False) -> str:
    from_name = "/dev/null" if added else f"a/{path}"
    to_name = "/dev/null" if deleted else f"b/{path}"
    original_lines = [] if added else original.splitlines()
    target_lines = [] if deleted else target.splitlines()
    return "\n".join(difflib.unified_diff(
        original_lines, target_lines, fromfile=from_name, tofile=to_name, lineterm=""
    ))


def _rule_map(rules_path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    from app.services.codeanalyzer import load_code_rules, RULES_PATH
    pack = load_code_rules(rules_path or RULES_PATH)
    return {rule["rule_id"]: rule for rule in pack["rules"]}


def refactor_codebase(scan: ScanResult, *, source_root: Path,
                      address_severities: set[str] | None = None,
                      address_rule_ids: set[str] | None = None,
                      apd_limit: int | None = None,
                      rules_path: Path | str | None = None) -> RefactorResult:
    """Create a target draft tree and patch list for the addressed findings."""
    root = Path(source_root)
    pack_rules = _rule_map(rules_path)
    limit = int(apd_limit or 24)
    target_root = Path(tempfile.mkdtemp(prefix="preflight-code-target-"))
    patches: list[dict[str, Any]] = []
    target_texts: dict[str, str] = {}
    added_files: list[dict[str, Any]] = []
    deleted_files: list[str] = []
    overrides: dict[str, str] = {}
    errors: list[str] = []

    addressed: list[CodeFinding] = []
    for finding in scan.findings:
        if address_severities is not None and finding.severity.value not in address_severities:
            continue
        if address_rule_ids is not None and finding.rule_id not in address_rule_ids:
            continue
        addressed.append(finding)

    by_path: dict[str, list[CodeFinding]] = {}
    for finding in addressed:
        by_path.setdefault(finding.path, []).append(finding)

    supporting: dict[str, tuple[str, list[str], list[str]]] = {}
    # path -> (content, finding_ids, rule_ids)

    for file_info in scan.files:
        relative = file_info["path"]
        raw = scan.source_texts.get(relative, "")
        if not raw:
            continue
        kind = file_info["kind"]
        findings = by_path.get(relative, [])
        target_path = relative
        if not findings:
            target_text = raw
        else:
            target_text = raw
            notes: list[str] = []
            strategies: list[str] = []
            rule_ids = sorted({item.rule_id for item in findings})
            for rule_id in rule_ids:
                if rule_id in {"PF-CODE-SQL-001", "PF-CODE-SQL-002"}:
                    target_text, _count, step_notes = _rewrite_sql(target_text, kind)
                    support_path, content = _gosu_data_access_draft(relative, raw)
                    supporting[support_path] = (
                        content,
                        [item.finding_id for item in findings
                         if item.rule_id in {"PF-CODE-SQL-001", "PF-CODE-SQL-002"}],
                        ["PF-CODE-SQL-001", "PF-CODE-SQL-002"],
                    )
                elif rule_id == "PF-CODE-SQL-003":
                    deleted_files.append(relative)
                    target_text = ""
                    step_notes = ["quarantined raw SQL script"]
                elif rule_id == "PF-CODE-SRV-001":
                    target_text, _count, step_notes = _strip_servlet(target_text, kind)
                    if kind in {"gosu", "java"}:
                        slug = _slug(relative)
                        support_path = f"config/cloudapi/{slug}-ext.yaml"
                        supporting[support_path] = (
                            _cloud_api_config(relative, _class_name(relative)),
                            [item.finding_id for item in findings],
                            ["PF-CODE-SRV-001"],
                        )
                        resource_path, resource_content = _jaxrs_resource_draft(relative, raw)
                        supporting[resource_path] = (
                            resource_content,
                            [item.finding_id for item in findings],
                            ["PF-CODE-SRV-001"],
                        )
                    else:
                        step_notes.append(
                            "legacy XML servlet descriptor replaced; the source-class patch carries the Cloud API route"
                        )
                elif rule_id == "PF-CODE-MSG-001":
                    target_text, _count, step_notes = _strip_messaging(target_text, kind)
                    if kind in {"gosu", "java"}:
                        slug = _slug(relative)
                        support_path = f"config/appevents/{slug}-publication.yaml"
                        supporting[support_path] = (
                            _app_events_config(relative, _class_name(relative)),
                            [item.finding_id for item in findings],
                            ["PF-CODE-MSG-001"],
                        )
                    else:
                        step_notes.append(
                            "legacy XML transport descriptor replaced; the source-class patch carries the App Events route"
                        )
                elif rule_id == "PF-CODE-API-001":
                    target_text, _count, step_notes = _strip_unsupported(target_text, kind)
                elif rule_id == "PF-CODE-API-002":
                    target_text, _count, step_notes = _strip_internal(target_text, kind)
                elif rule_id == "PF-CODE-SEC-001":
                    target_text, _count, step_notes = _replace_secrets(target_text, kind)
                    names = {
                        match.group(1) for match in SECRET_KEYS.finditer(raw)
                        if is_sensitive_secret_key(match.group(1))
                    }
                    if names:
                        support_path = f"config/secrets/{_slug(relative)}-secret-refs.yaml"
                        supporting[support_path] = (
                            _secret_refs(relative, names),
                            [item.finding_id for item in findings],
                            ["PF-CODE-SEC-001"],
                        )
                elif rule_id == "PF-CODE-SEC-002":
                    target_text, _count, step_notes = _replace_weak_crypto(target_text, kind)
                elif rule_id == "PF-CODE-MT-001":
                    target_text, _count, step_notes = _remove_static(target_text, kind)
                elif rule_id == "PF-CODE-MT-002":
                    target_text, _count, step_notes = _remove_process(target_text, kind)
                elif rule_id == "PF-CODE-TX-001":
                    target_text, _count, step_notes = _remove_commit(target_text, kind)
                elif rule_id == "PF-CODE-EXC-001":
                    target_text, _count, step_notes = _fix_empty_catches(target_text, kind, relative)
                elif rule_id == "PF-CODE-APD-001":
                    step_notes = ["recorded a codegen nameOverride for the long APD type"]
                    for finding in findings:
                        type_match = re.search(r"APD type '([^']+)'", finding.message)
                        if type_match:
                            type_name = type_match.group(1)
                            truncated, config = _codegen_override(type_name, limit)
                            overrides[type_name] = truncated
                            support_path = (
                                f"config/codegen/{_slug(relative)}-{_slug(type_name)}"
                                "_codegen_config_ext-1.0.yaml"
                            )
                            supporting[support_path] = (
                                config,
                                [finding.finding_id],
                                ["PF-CODE-APD-001"],
                            )
                elif rule_id == "PF-CODE-GUNIT-001":
                    target_text, _count, step_notes = _strip_gunit_db(target_text, kind)
                elif rule_id == "PF-CODE-LOG-001":
                    target_text, _count, step_notes = _strip_pii_logs(target_text, kind)
                else:
                    step_notes = [f"no automated transform; manual review required for {rule_id}"]
                strategies.extend(step_notes)

            # XML integration descriptors become a parseable placeholder rather
            # than a half-commented document.
            if kind == "xml" and any(
                rule_id in {"PF-CODE-SRV-001", "PF-CODE-MSG-001", "PF-CODE-API-001", "PF-CODE-SQL-001"}
                for rule_id in rule_ids
            ):
                target_text = _xml_placeholder(relative, rule_ids)
                strategies.append("replaced the legacy XML integration descriptor with a reviewable placeholder")

            # Fail-safe scrub for any addressed regex rule left over.
            scrub_rules = [pack_rules[rule_id] for rule_id in rule_ids if rule_id in pack_rules]
            target_text, scrubbed = _scrub_residual(target_text, kind, scrub_rules)
            if scrubbed:
                strategies.append(f"fail-safe removed {scrubbed} residual pattern line(s)")

            target_text = _add_header(target_text, kind)
            if relative.endswith((".gs", ".java")) and target_text.strip() == _header(kind).strip():
                # Keep a reviewable placeholder instead of an empty source file.
                target_text += (
                    "// Original file contained only removed cloud blockers. "
                    "See the migration report before deleting it.\n"
                )
            target_texts[relative] = target_text

        # Write the target file unless it was quarantined.
        if relative in deleted_files:
            continue
        destination = target_root / target_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(target_text, encoding="utf-8")

        if findings:
            diff = _diff(raw, target_text, relative)
            diff_redacted = any(item.rule_id == "PF-CODE-SEC-001" for item in findings)
            display_diff = diff
            if diff_redacted:
                display_diff, _ = redact_excerpt(diff, all_quoted_strings=True)
            patch = {
                "patch_id": f"CP-{len(patches) + 1:03d}",
                "source_path": relative,
                "target_path": target_path,
                "finding_ids": [item.finding_id for item in findings],
                "rule_ids": sorted({item.rule_id for item in findings}),
                "strategy": "; ".join(dict.fromkeys(strategies)) or "structural refactor",
                "diff": display_diff,
                "source_sha256": _sha(raw),
                "target_sha256": _sha(target_text),
                "risk": "high" if any(item.severity.value == "error" for item in findings) else "medium",
                "semantic_review": True,
                "diff_redacted": diff_redacted,
                "approval": "pending",
            }
            patches.append(patch)

    # Deleted-file patches are emitted after file patches.
    for relative in deleted_files:
        raw = scan.source_texts.get(relative, "")
        patches.append({
            "patch_id": f"CP-{len(patches) + 1:03d}",
            "source_path": relative,
            "target_path": relative,
            "finding_ids": [item.finding_id for item in by_path.get(relative, [])],
            "rule_ids": sorted({item.rule_id for item in by_path.get(relative, [])}),
            "strategy": "quarantined raw SQL script; do not deploy",
            "diff": _diff(raw, "", relative, deleted=True),
            "source_sha256": _sha(raw),
            "target_sha256": _sha(""),
            "risk": "high",
            "semantic_review": True,
            "diff_redacted": False,
            "approval": "pending",
        })

    # Supporting cloud configuration drafts.
    for relative, (content, finding_ids, rule_ids) in sorted(supporting.items()):
        destination = target_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        added_files.append({
            "path": relative,
            "bytes": len(content.encode("utf-8")),
            "sha256": _sha(content),
        })
        patches.append({
            "patch_id": f"CP-{len(patches) + 1:03d}",
            "source_path": None,
            "target_path": relative,
            "finding_ids": finding_ids,
            "rule_ids": rule_ids,
            "strategy": "generated cloud configuration draft",
            "diff": _diff("", content, relative, added=True),
            "source_sha256": _sha(""),
            "target_sha256": _sha(content),
            "risk": "medium",
            "semantic_review": True,
            "diff_redacted": False,
            "approval": "pending",
        })

    return RefactorResult(
        target_root=target_root,
        patches=patches,
        target_texts=target_texts,
        added_files=added_files,
        deleted_files=sorted(deleted_files),
        overrides=overrides,
        errors=errors,
    )


def apply_unified_diff(original: str, diff: str) -> str:
    """Apply a unified diff produced by :func:`_diff`.

    Used by the Critic to prove that the displayed patch and the target draft
    describe the same edit. It is intentionally small and strict.
    """
    original_lines = original.splitlines()
    source_index = 0
    output: list[str] = []
    hunk_header = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    lines = diff.splitlines()
    cursor = 0
    while cursor < len(lines):
        line = lines[cursor]
        if hunk_header.match(line):
            header = hunk_header.match(line)
            start = int(header.group(1))
            while source_index < start - 1:
                output.append(original_lines[source_index])
                source_index += 1
            cursor += 1
            while cursor < len(lines) and not hunk_header.match(lines[cursor]):
                body = lines[cursor]
                if body.startswith("\\ No newline"):
                    cursor += 1
                    continue
                if not body:
                    output.append("")
                    source_index += 1
                elif body.startswith(" "):
                    output.append(body[1:])
                    source_index += 1
                elif body.startswith("+"):
                    output.append(body[1:])
                elif body.startswith("-"):
                    source_index += 1
                cursor += 1
            continue
        cursor += 1
    while source_index < len(original_lines):
        output.append(original_lines[source_index])
        source_index += 1
    return "\n".join(output) + ("\n" if original.endswith("\n") or diff.endswith("\n") else "")
