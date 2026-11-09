"""Shared secret-redaction utility tests."""

from __future__ import annotations

from app.models import Confidence, Locator, LocatorKind, make_evidence
from app.services.redaction import redact_evidence, redact_excerpt


def test_assignment_values_are_fingerprinted() -> None:
    text, changed = redact_excerpt('var apiKey = "sk-live-9f3a7c2b6d1e"')
    assert changed is True
    assert "sk-live-9f3a7c2b6d1e" not in text
    assert "[REDACTED:" in text


def test_typed_assignment_and_bearer_token_are_redacted() -> None:
    text, changed = redact_excerpt(
        'var secret : String = "s3cr3t-live-value"\nAuthorization: Bearer abcdef123456'
    )
    assert changed is True
    assert "s3cr3t-live-value" not in text
    assert "abcdef123456" not in text


def test_safe_suffix_keys_are_left_alone() -> None:
    text, changed = redact_excerpt(
        'var tokenUrl = "https://example.test/token"\nvar passwordPolicy = "standard-policy"'
    )
    assert changed is False
    assert text == 'var tokenUrl = "https://example.test/token"\nvar passwordPolicy = "standard-policy"'


def test_redaction_is_idempotent() -> None:
    once, first = redact_excerpt('password = "hunter2"')
    twice, second = redact_excerpt(once)
    assert first is True
    assert second is False
    assert twice == once


def test_yaml_mapping_values_and_parser_context_are_redacted() -> None:
    text, changed = redact_excerpt(
        'while scanning a quoted scalar\n'
        '    password: "hunter2"\n'
        '    apiKey: "sk-live-abc123"\n'
        "                ^ (line: 1)"
    )
    assert changed is True
    assert "hunter2" not in text
    assert "sk-live-abc123" not in text
    assert text.count("[REDACTED:") == 2


def test_yaml_mapping_does_not_over_redact_safe_names() -> None:
    text = 'tokenUrl: "https://example.test/token"\ntokenizer: "whitespace"\npasswordPolicy: "standard"'
    redacted, changed = redact_excerpt(text)
    assert changed is False
    assert redacted == text


def test_yaml_unquoted_secret_is_redacted() -> None:
    text, changed = redact_excerpt("types:\n  password: Zx9Qw2Lm7Pk4Vn8Rt: extra\n")
    assert changed is True
    assert "Zx9Qw2Lm7Pk4Vn8Rt" not in text
    assert "password: [REDACTED:" in text


def test_yaml_single_quoted_secret_is_redacted() -> None:
    text, changed = redact_excerpt("  api_key: 'Zx9Qw2Lm7Pk4Vn8Rt'\n")
    assert changed is True
    assert "Zx9Qw2Lm7Pk4Vn8Rt" not in text
    assert "api_key: '[REDACTED:" in text


def test_yaml_double_quoted_secret_is_redacted() -> None:
    text, changed = redact_excerpt('  client_secret: "Zx9Qw2Lm7Pk4Vn8Rt"\n')
    assert changed is True
    assert "Zx9Qw2Lm7Pk4Vn8Rt" not in text
    assert 'client_secret: "[REDACTED:' in text


def test_yaml_secret_with_colons_and_comment_is_redacted() -> None:
    text, changed = redact_excerpt(
        "  password: user:Zx9Qw2Lm7Pk4Vn8Rt:more # staging\n"
    )
    assert changed is True
    assert "Zx9Qw2Lm7Pk4Vn8Rt" not in text
    assert "user:" not in text
    assert " # staging" in text


def test_yaml_tab_indented_secret_is_redacted() -> None:
    text, changed = redact_excerpt("\tcredential:\tZx9Qw2Lm7Pk4Vn8Rt\n")
    assert changed is True
    assert "Zx9Qw2Lm7Pk4Vn8Rt" not in text
    assert "\tcredential:\t[REDACTED:" in text


def test_yaml_bad_escape_and_unterminated_quote_are_redacted() -> None:
    text, changed = redact_excerpt(
        '  token: "bad\\qZx9Qw2Lm7Pk4Vn8Rt"\n'
        '  password: "unterminated-Zx9Qw2Lm7Pk4Vn8Rt\n'
    )
    assert changed is True
    assert "Zx9Qw2Lm7Pk4Vn8Rt" not in text
    assert text.count("[REDACTED:") == 2


def test_yaml_redaction_is_idempotent_for_all_quote_styles() -> None:
    text = (
        "password: hunter2\n"
        "api_key: 'sk-live-abc123'\n"
        'client_secret: "cs-live-def456"\n'
    )
    once, first = redact_excerpt(text)
    twice, second = redact_excerpt(once)
    assert first is True
    assert second is False
    assert twice == once


def test_redact_evidence_preserves_locator_and_updates_fingerprint() -> None:
    evidence = make_evidence(
        evidence_id="EV-0001",
        path="gsrc/acme/Leaky.gs",
        locator=Locator(kind=LocatorKind.LINE, value="line 7", line=7),
        excerpt='var password = "hunter2"',
        method="lexer",
        confidence=Confidence.PARSED,
    )
    durable = redact_evidence([evidence])
    assert durable[0].locator == evidence.locator
    assert durable[0].evidence_id == evidence.evidence_id
    assert "hunter2" not in durable[0].excerpt
    assert durable[0].redacted is True
    assert durable[0].excerpt_sha != evidence.excerpt_sha
    # The original in-memory evidence still feeds evaluation untouched.
    assert evidence.excerpt == 'var password = "hunter2"'
