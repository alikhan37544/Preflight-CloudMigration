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


def test_xml_elements_and_cdata_secrets_are_redacted() -> None:
    text = (
        '<credential><password>hunter2</password></credential>\n'
        '<secret><![CDATA[sk-live-cdata1234]]></secret>\n'
        '<token attr="plain">tok-live-element1234</token>'
    )
    redacted, changed = redact_excerpt(text)
    assert changed is True
    assert "hunter2" not in redacted
    assert "sk-live-cdata1234" not in redacted
    assert "tok-live-element1234" not in redacted
    assert "<password>[REDACTED:" in redacted
    assert "<![CDATA[[REDACTED:" in redacted
    assert "<token attr=\"plain\">[REDACTED:" in redacted
    twice, again = redact_excerpt(redacted)
    assert again is False
    assert twice == redacted


def test_xml_safe_elements_attributes_and_type_names_are_left_alone() -> None:
    text = (
        '<passwordPolicy>standard-policy</passwordPolicy>\n'
        '<tokenUrl>https://example.test/token</tokenUrl>\n'
        '<field name="Password" type="String"/>\n'
        '<column name="TokenCount" type="Integer"/>'
    )
    redacted, changed = redact_excerpt(text)
    assert changed is False
    assert redacted == text


def test_typed_declaration_redacts_only_the_value_not_the_type() -> None:
    redacted, changed = redact_excerpt('var secret : String = "hunter2"')
    assert changed is True
    assert "hunter2" not in redacted
    assert 'var secret : String = "[REDACTED:' in redacted
    # The type name must not be mistaken for an unquoted value.
    assert "String" in redacted
    assert "[REDACTED:b2ef230e]" not in redacted


def test_yaml_block_scalar_after_prose_is_redacted() -> None:
    text = (
        "Reviewer note: password: |\n"
        "  hunter2\n"
        "  second-secret\n"
        "  tokenUrl: https://example.test/token\n"
        "next: safe\n"
    )
    redacted, changed = redact_excerpt(text)
    assert changed is True
    assert "hunter2" not in redacted
    assert "second-secret" not in redacted
    assert "Reviewer note: password: |" in redacted
    assert "next: safe" in redacted
    twice, again = redact_excerpt(redacted)
    assert again is False
    assert twice == redacted


def test_xml_attributes_are_redacted_without_touching_bindings() -> None:
    text = (
        '<column name="PasswordHash" default="hunter2" type="Text"/>\n'
        '<connection password="s3cr3t-value" tokenUrl="https://example.test/token"/>\n'
        '<TextInput id="VehicleType" value="VehicleType"/>'
    )
    redacted, changed = redact_excerpt(text)
    assert changed is True
    assert "hunter2" not in redacted
    assert "s3cr3t-value" not in redacted
    assert 'default="[REDACTED:' in redacted
    assert 'password="[REDACTED:' in redacted
    assert 'value="VehicleType"' in redacted
    assert 'tokenUrl="https://example.test/token"' in redacted


def test_json_secret_keys_are_redacted_and_safe_keys_are_not() -> None:
    text = (
        '{"password": "hunter2", "token": "tok-live-abc123", '
        '"tokenUrl": "https://example.test/token", "passwordPolicy": "standard"}'
    )
    redacted, changed = redact_excerpt(text)
    assert changed is True
    assert "hunter2" not in redacted
    assert "tok-live-abc123" not in redacted
    assert '"tokenUrl": "https://example.test/token"' in redacted
    assert '"passwordPolicy": "standard"' in redacted


def test_yaml_block_scalar_body_is_redacted() -> None:
    text = (
        "credentials:\n"
        "  password: |\n"
        "    hunter2\n"
        "    second-secret\n"
        "  token: >-\n"
        "    tok-live-abc123\n"
        "  tokenUrl: https://example.test/token\n"
    )
    redacted, changed = redact_excerpt(text)
    assert changed is True
    assert "hunter2" not in redacted
    assert "second-secret" not in redacted
    assert "tok-live-abc123" not in redacted
    assert "https://example.test/token" in redacted
    twice, again = redact_excerpt(redacted)
    assert again is False
    assert twice == redacted


def test_single_quoted_assignments_and_labelled_values_are_redacted() -> None:
    text = (
        "var password = 'hunter2'\n"
        "var token : String = 'tok-live-abc123'\n"
        "var passwordPolicy = 'standard-policy'\n"
        'reason: password "hunter2" and token "sk-live-reason1234"'
    )
    redacted, changed = redact_excerpt(text)
    assert changed is True
    assert "hunter2" not in redacted
    assert "tok-live-abc123" not in redacted
    assert "sk-live-reason1234" not in redacted
    assert "passwordPolicy = 'standard-policy'" in redacted


def test_unquoted_reviewer_note_secrets_are_redacted() -> None:
    text = "reviewer note password=hunter2 token: abc123 tokenUrl=https://example.test/token"
    redacted, changed = redact_excerpt(text)
    assert changed is True
    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "tokenUrl=https://example.test/token" in redacted
    assert redact_excerpt(redacted)[1] is False


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
