"""Shared secret-redaction utility tests."""

from __future__ import annotations

from app.services.redaction import redact_excerpt


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
