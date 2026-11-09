"""Central secret redaction for persisted evidence excerpts.

Every excerpt that leaves the analysis pipeline (discovery evidence, review
evidence, and the review packet) passes through :func:`redact_excerpt`. Values
are replaced with a short SHA-256 fingerprint so reviewers can correlate a
finding without storing the secret itself. Locators are never changed.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Evidence

# Assignment forms used by Gosu and similar configuration code, including typed
# declarations such as ``var secret : String = "..."`` and property writes.
SECRET_KEYS = re.compile(
    r'(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[A-Za-z_][A-Za-z0-9_.<>\[\]]*)?\s*=\s*"((?:\\.|[^"\\])*)"'
)
# Single-quoted assignments are common in JavaScript-ish configuration snippets
# and parser error text (``var password = 'hunter2'``).
SINGLE_QUOTED_SECRET_KEYS = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[A-Za-z_][A-Za-z0-9_.<>\[\]]*)?\s*=\s*'((?:\\.|[^'\\])*)'"
)
# Unquoted assignment/colon form used by reviewer notes and malformed config
# errors (``password=hunter2`` or ``token: abc123``). The value stops at obvious
# delimiters so surrounding prose and punctuation survive. The value is matched
# possessively and rejected when an assignment follows it, so a typed Gosu
# declaration (``var secret : String = "..."``) cannot redact its type name.
UNQUOTED_SECRET_KEYS = re.compile(
    r"""(?ix)
    \b(?P<key>[A-Za-z_][A-Za-z0-9_]*)
    [ \t]*(?::[ \t]*[A-Za-z_][A-Za-z0-9_.<>\[\]]*)?
    [ \t]*(?:=|:)[ \t]*
    (?P<value>[^\s,;)\]}"']++)(?![ \t]*=(?!=))
    """
)
# A sensitive label followed by a quoted value without an explicit assignment
# operator, e.g. ``password "hunter2"`` in a reviewer note or parser warning.
LABELLED_QUOTED_SECRET = re.compile(
    r"""(?ix)
    (?<!["'A-Za-z0-9_])
    (?P<key>[A-Za-z_][A-Za-z0-9_.-]*)
    [ \t]*(?:=|:)?[ \t]+
    (?P<quote>["'])
    (?P<value>(?:\\.|(?!(?P=quote)).)*)
    (?P=quote)
    """
)
# XML attribute form: ``password="hunter2"``. ``default`` is treated as a
# sensitive attribute in entity/config XML (``<column default="hunter2">``),
# while ordinary display attributes such as ``name`` and ``value`` are left
# untouched so evidence excerpts remain useful.
XML_SECRET_ATTRIBUTE = re.compile(
    r"""(?ix)
    \b(?P<key>[A-Za-z_][A-Za-z0-9_.:-]*)
    [ \t]*=[ \t]*
    (?P<quote>["'])
    (?P<value>(?:\\.|(?!(?P=quote)).)*)
    (?P=quote)
    """
)
XML_SENSITIVE_NAMES = {"default"}
# XML element bodies, including CDATA sections:
# ``<password>hunter2</password>`` and
# ``<secret><![CDATA[hunter2]]></secret>``. Only element names in the shared
# sensitive-name taxonomy are redacted; ordinary elements such as
# ``<tokenUrl>``, ``<passwordPolicy>`` and normal type attributes are untouched.
XML_ELEMENT_SECRET = re.compile(
    r"""(?isx)
    <(?P<tag>[A-Za-z_][A-Za-z0-9_.:-]*)(?:\s[^>]*)?>
    (?:
        <!\[CDATA\[(?P<cdata>.*?)\]\]>
        |
        (?P<text>[^<]*)
    )
    </(?P=tag)>
    """
)
# YAML block-scalar indicator anywhere on a line. Reviewer notes sometimes put
# the sensitive key after prose (``Reviewer note: password: |``), so the block
# body cannot be found by only anchoring at the start of the line.
YAML_BLOCK_SCALAR = re.compile(
    r"""(?ix)
    (?:^|[ \t])
    (?P<key>["']?[A-Za-z_][A-Za-z0-9_.-]*["']?)
    [ \t]*:[ \t]*
    (?P<indicator>[|>][+-]?)
    [ \t]*(?:\#.*)?$
    """
)
# JSON object form, including single-line documents where the YAML line matcher
# cannot see the key at the start of a line.
JSON_SECRET_KEY = re.compile(
    r"""(?ix)
    (?P<prefix>["'](?P<key>[A-Za-z_][A-Za-z0-9_.-]*)["'][ \t]*:[ \t]*)
    (?P<quote>["'])
    (?P<value>(?:\\.|(?!(?P=quote)).)*)
    (?P=quote)
    """
)
# YAML mapping form. Parser errors quote the offending source line, so warnings
# such as ``password: "hunter2"`` must be filtered before they are persisted.
# The RHS is deliberately not constrained to one quote style: malformed YAML
# errors reproduce single-quoted and unquoted scalars just as readily.
YAML_SECRET_LINE = re.compile(
    r"""(?ix)
    ^[ \t]*(?:-[ \t]+)?
    (?P<key>["']?[A-Za-z_][A-Za-z0-9_.-]*["']?)
    [ \t]*:[ \t]*
    (?P<rhs>.*)$
    """
)
SECRET_PLACEHOLDERS = {
    "changeme", "<placeholder>", "placeholder", "***", "", "redacted", "example",
    "${secret}", "{{secret}}", "replace_me", "replaceme", "todo", "tbd", "n/a",
    "none", "null", "********", "bearer", "basic", "prefix",
}
SENSITIVE_NAME_PARTS = {
    "secret", "password", "passwd", "token", "credential", "apikey",
    "privatekey", "accesskey", "secretkey", "clientsecret", "authtoken", "apitoken",
}
SAFE_KEY_SUFFIXES = {"timeout", "length", "name", "url", "uri", "endpoint", "count", "type", "policy"}
SAFE_KEY_PREFIX_PARTS = {"api", "private", "access", "secret", "client", "signing", "encryption"}

# Live-looking tokens used by the synthetic fixtures and generated secrets.
LIVE_TOKEN = re.compile(
    r"(?i)\b[A-Za-z0-9][A-Za-z0-9._~+/=-]{1,}-live-[A-Za-z0-9._~+/=-]{4,}\b"
)
BEARER_TOKEN = re.compile(
    r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]{8,})"
)
QUOTED_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
REDACTED_VALUE = re.compile(r"^\[REDACTED(?::[0-9a-f]{8})?\]$")


def fingerprint(value: str) -> str:
    """Stable 8-hex fingerprint retained in place of a redacted value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def is_sensitive_secret_key(name: str) -> bool:
    """Apply the shared key-name taxonomy used by review detection and redaction."""
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    parts = [part for part in re.split(r"[_\-\s]+", normalized) if part]
    if parts and parts[-1] in SAFE_KEY_SUFFIXES:
        return False
    sensitive = any(part in SENSITIVE_NAME_PARTS for part in parts)
    if not sensitive and normalized.endswith("_key"):
        sensitive = bool(set(parts[:-1]) & SAFE_KEY_PREFIX_PARTS)
    return sensitive


def _marker(value: str) -> str:
    return f"[REDACTED:{fingerprint(value)}]"


def _redact_assignment(match: re.Match[str]) -> str:
    if not is_sensitive_secret_key(match.group(1)):
        return match.group(0)
    value = match.group(2)
    stripped = value.strip()
    if REDACTED_VALUE.match(stripped):
        return match.group(0)
    start = match.start(2) - match.start(0)
    end = match.end(2) - match.start(0)
    return match.group(0)[:start] + _marker(value) + match.group(0)[end:]


def _redact_live_token(match: re.Match[str]) -> str:
    value = match.group(0)
    if REDACTED_VALUE.match(value.strip()):
        return value
    return _marker(value)


def _redact_bearer(match: re.Match[str]) -> str:
    value = match.group(2)
    if REDACTED_VALUE.match(value.strip()):
        return match.group(0)
    return match.group(1) + _marker(value)


def _redact_quoted(match: re.Match[str]) -> str:
    value = match.group(0)[1:-1]
    if REDACTED_VALUE.match(value.strip()):
        return match.group(0)
    return f'"{_marker(value)}"'


def _redact_quoted_value(query: str, match: re.Match[str]) -> str:
    """Redact the ``value`` group of an XML/JSON/labelled match."""
    key = match.group("key")
    if query == "xml":
        sensitive = is_sensitive_secret_key(key) or key.lower() in XML_SENSITIVE_NAMES
    else:
        sensitive = is_sensitive_secret_key(key)
    if not sensitive:
        return match.group(0)
    value = match.group("value")
    if not value or REDACTED_VALUE.match(value.strip()):
        return match.group(0)
    start, end = match.start("value"), match.end("value")
    prefix = match.group(0)[:start - match.start()]
    suffix = match.group(0)[end - match.start():]
    return prefix + _marker(value) + suffix


def _redact_json(match: re.Match[str]) -> str:
    return _redact_quoted_value("json", match)


def _redact_xml(match: re.Match[str]) -> str:
    return _redact_quoted_value("xml", match)


def _redact_xml_element(match: re.Match[str]) -> str:
    """Redact a sensitive XML element body while preserving its tags.

    Plain text and CDATA bodies are fingerprinted as a unit. Leading and
    trailing whitespace is preserved so the surrounding document stays legible.
    """
    tag = match.group("tag").rsplit(":", 1)[-1]
    if not (is_sensitive_secret_key(tag) or tag.lower() in XML_SENSITIVE_NAMES):
        return match.group(0)
    cdata = match.group("cdata")
    if cdata is not None:
        value = cdata
        start, end = match.start("cdata"), match.end("cdata")
    else:
        value = match.group("text") or ""
        start, end = match.start("text"), match.end("text")
    stripped = value.strip()
    if not stripped or REDACTED_VALUE.match(stripped):
        return match.group(0)
    leading = value[:len(value) - len(value.lstrip())]
    trailing = value[len(value.rstrip()):]
    replacement = leading + _marker(stripped) + trailing
    return match.group(0)[:start - match.start()] + replacement + match.group(0)[end - match.start():]


def _redact_labelled(match: re.Match[str]) -> str:
    return _redact_quoted_value("labelled", match)


def _redact_single_assignment(match: re.Match[str]) -> str:
    if not is_sensitive_secret_key(match.group(1)):
        return match.group(0)
    value = match.group(2)
    if REDACTED_VALUE.match(value.strip()):
        return match.group(0)
    start = match.start(2) - match.start(0)
    end = match.end(2) - match.start(0)
    return match.group(0)[:start] + _marker(value) + match.group(0)[end:]


def _redact_unquoted_assignment(match: re.Match[str]) -> str:
    if not is_sensitive_secret_key(match.group("key")):
        return match.group(0)
    value = match.group("value")
    lowered = value.strip().lower()
    if (not value or REDACTED_VALUE.match(value.strip())
            or value.startswith("[REDACTED")
            or value in {"|", "|-", "|+", ">", ">-", ">+"}
            or lowered in SECRET_PLACEHOLDERS
            or lowered in {"true", "false", "null", "none", "undefined"}
            or lowered.startswith(("system.", "getenv", "env.", "${", "{{"))):
        return match.group(0)
    start, end = match.start("value"), match.end("value")
    prefix = match.group(0)[:start - match.start()]
    suffix = match.group(0)[end - match.start():]
    return prefix + _marker(value) + suffix


def _quoted_scalar(rhs: str) -> tuple[int, str] | None:
    """Return ``(end_index, inner_value)`` for a quoted YAML scalar.

    ``None`` means the quote was never closed (a common way for malformed YAML
    parser errors to reproduce the offending line). Single-quoted YAML escapes
    an embedded quote by doubling it; double-quoted YAML uses a backslash.
    """
    quote = rhs[0]
    index = 1
    while index < len(rhs):
        char = rhs[index]
        if quote == '"' and char == "\\":
            index += 2
            continue
        if char == quote:
            if quote == "'" and index + 1 < len(rhs) and rhs[index + 1] == "'":
                index += 2
                continue
            return index + 1, rhs[1:index]
        index += 1
    return None


def _comment_start(rhs: str) -> int | None:
    """Index of a YAML comment marker outside a scalar, if any."""
    for index, char in enumerate(rhs):
        if char == "#" and (index == 0 or rhs[index - 1] in " \t"):
            return index
    return None


def _redact_yaml_line(line: str) -> str:
    """Redact one YAML mapping line without changing its key or indentation."""
    match = YAML_SECRET_LINE.match(line)
    if match is None:
        return line
    key = match.group("key").strip("\"'")
    if not is_sensitive_secret_key(key):
        return line
    rhs = match.group("rhs")
    if not rhs:
        return line

    if rhs[0] in "\"'":
        parsed = _quoted_scalar(rhs)
        if parsed is None:
            # Unterminated quote: everything after the opener is scalar text.
            value = rhs[1:]
            if not value or REDACTED_VALUE.match(value.strip()):
                return line
            replacement = _marker(value)
        else:
            end, value = parsed
            if not value or REDACTED_VALUE.match(value.strip()):
                return line
            replacement = rhs[0] + _marker(value) + rhs[0] + rhs[end:]
    else:
        comment = _comment_start(rhs)
        scalar = rhs if comment is None else rhs[:comment]
        trimmed = scalar.rstrip(" \t")
        value = trimmed
        if not value.strip() or value.strip() in {"|", "|-", "|+", ">", ">-", ">+"}:
            return line
        if REDACTED_VALUE.match(value.strip()):
            return line
        replacement = _marker(value) + rhs[len(trimmed):]

    return line[:match.start("rhs")] + replacement + line[match.end("rhs"):]


def _redact_yaml_lines(text: str) -> str:
    """Apply :func:`_redact_yaml_line` while preserving every line ending.

    A sensitive key with a block scalar (``password: |``) has no value on the
    key line. Its indented body is redacted as a unit instead of being left in
    the persisted excerpt.
    """
    pieces: list[str] = []
    block_indent: int | None = None
    for line in text.splitlines(keepends=True):
        if line.endswith("\r\n"):
            body, ending = line[:-2], "\r\n"
        elif line.endswith(("\n", "\r")):
            body, ending = line[:-1], line[-1]
        else:
            body, ending = line, ""
        if block_indent is not None:
            if not body.strip():
                pieces.append(body + ending)
                continue
            indent = len(body) - len(body.lstrip(" \t"))
            if indent > block_indent:
                stripped = body.strip()
                if REDACTED_VALUE.match(stripped):
                    pieces.append(body + ending)
                else:
                    pieces.append(body[:indent] + _marker(stripped) + ending)
                continue
            block_indent = None
        processed = _redact_yaml_line(body)
        pieces.append(processed + ending)
        block_indent = _block_scalar_indent(processed)
    return "".join(pieces)


def _block_scalar_indent(line: str) -> int | None:
    """Indentation of a sensitive YAML key whose value is a block scalar.

    The key may follow prose on the same line (``Reviewer note: password: |``);
    the block body is still indented deeper than that line, so its indentation
    is used to delimit the scalar.
    """
    for match in YAML_BLOCK_SCALAR.finditer(line):
        key = match.group("key").strip("\"'")
        if is_sensitive_secret_key(key):
            return len(line) - len(line.lstrip(" \t"))
    return None


def redact_excerpt(text: str, *, all_quoted_strings: bool = False,
                   extra_values: Iterable[str] = ()) -> tuple[str, bool]:
    """Redact secret values in ``text`` and report whether anything changed.

    ``all_quoted_strings`` is used for the dedicated hard-coded secret finding:
    a three-line excerpt can contain neighbouring literal values, so every quoted
    literal is fingerprinted. ``extra_values`` lets that rule also remove secret
    values that appear unquoted in an adjacent comment. Line locators remain
    untouched.
    """
    if not text:
        return text, False
    original = text
    for value in sorted({value for value in extra_values if value}, key=len, reverse=True):
        if not REDACTED_VALUE.match(value.strip()):
            text = text.replace(value, _marker(value))
    text = _redact_yaml_lines(text)
    text = JSON_SECRET_KEY.sub(_redact_json, text)
    text = XML_ELEMENT_SECRET.sub(_redact_xml_element, text)
    text = XML_SECRET_ATTRIBUTE.sub(_redact_xml, text)
    text = SECRET_KEYS.sub(_redact_assignment, text)
    text = SINGLE_QUOTED_SECRET_KEYS.sub(_redact_single_assignment, text)
    text = UNQUOTED_SECRET_KEYS.sub(_redact_unquoted_assignment, text)
    text = LABELLED_QUOTED_SECRET.sub(_redact_labelled, text)
    text = LIVE_TOKEN.sub(_redact_live_token, text)
    text = BEARER_TOKEN.sub(_redact_bearer, text)
    if all_quoted_strings:
        text = QUOTED_STRING.sub(_redact_quoted, text)
    return text, text != original


def redact_evidence(items: Sequence["Evidence"]) -> list["Evidence"]:
    """Copy evidence with redacted excerpts and matching hashes.

    Locators, IDs, paths, and confidence are unchanged. Callers persist the
    returned copies; the original objects remain available to in-memory stages
    that need the source text.
    """
    redacted: list["Evidence"] = []
    for item in items:
        excerpt, changed = redact_excerpt(item.excerpt)
        if changed:
            item = item.model_copy(update={
                "excerpt": excerpt,
                "excerpt_sha": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                "redacted": True,
            })
        redacted.append(item)
    return redacted


# Descriptive alias for callers that prefer the longer name.
redact_secrets = redact_excerpt
