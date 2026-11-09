"""Central secret redaction for persisted evidence excerpts.

Every excerpt that leaves the analysis pipeline (discovery evidence, review
evidence, and the review packet) passes through :func:`redact_excerpt`. Values
are replaced with a short SHA-256 fingerprint so reviewers can correlate a
finding without storing the secret itself. Locators are never changed.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

# Assignment forms used by Gosu and similar configuration code, including typed
# declarations such as ``var secret : String = "..."`` and property writes.
SECRET_KEYS = re.compile(
    r'(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[A-Za-z_][A-Za-z0-9_.<>\[\]]*)?\s*=\s*"((?:\\.|[^"\\])*)"'
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
    text = SECRET_KEYS.sub(_redact_assignment, text)
    text = LIVE_TOKEN.sub(_redact_live_token, text)
    text = BEARER_TOKEN.sub(_redact_bearer, text)
    if all_quoted_strings:
        text = QUOTED_STRING.sub(_redact_quoted, text)
    return text, text != original


# Descriptive alias for callers that prefer the longer name.
redact_secrets = redact_excerpt
