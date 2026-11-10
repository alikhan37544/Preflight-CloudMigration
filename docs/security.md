# PreFlight Security Contract

**Mode:** local single-user product. No authentication, no multi-tenancy, no network egress by default.
**Binding:** `127.0.0.1` only.

## Threat model

| Asset | Threat | Control |
|---|---|---|
| Source snapshot | Unauthorised upload/leak | Local-only default; no telemetry; optional LLM off |
| Uploaded archive | Zip-slip, bomb, symlink escape | Canonicalise, size/ratio limits, reject symlinks/absolute paths |
| XML/YAML | XXE, entity expansion, unsafe tags | `lxml` safe parser options; `safe_load` |
| Source text | Prompt injection | No tools; evidence IDs; schema validation |
| Draft output | Path traversal | Resolve under run directory; allowlist |
| Packet/logs | Raw secret leakage | Redact at capture; fingerprint only; tests |
| Packet | Tampering | Packet hash + content digests; `preflight verify-packet` |
| Audit log | Tampering | Hash chain; `preflight verify-audit` (audit chain only) |
| Browser session | CSRF, XSS | CSRF token; SameSite=Strict; autoescape; CSP |

## Controls

- CSRF synchronizer token per session, validated on every mutating POST from the `X-CSRF-Token` header or a form field; tokens in the query string are rejected (they leak into logs and referrers); rotation on session change.
- Session cookie is HMAC-signed with the runtime secret; arbitrary chosen session values are replaced. `HttpOnly`, `SameSite=Strict`, `Path=/`.
- Host/Origin allowlist; missing/empty `Host` is rejected and `Origin` is compared exactly as scheme+host+port against configured loopback origins (plus exact same-origin matches). Reject cross-origin mutations.
- CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`.
- Jinja2 autoescape; no `|safe`; JS uses `textContent`.
- Zip limits: 20,000 files, 500 MB compressed, 2 GB uncompressed, 100:1 ratio, per-entry uncompressed cap; reject encrypted entries, symlinks, hardlinks/link metadata, special files, empty/`.` entries, absolute paths, `..`, NUL, drive letters. Size/ratio checks apply to every entry, including small ones.
- XML: `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`.
- YAML: ruamel token scan rejects every explicit tag (`!!`, single-`!`, verbatim `!<...>`); no arbitrary constructors.
- Intake enumerates symlinks as explicit `unsupported` artifacts (never followed, never hidden) and marks malformed JSON/YAML `corrupt` before parsing.
- Artifact reads: allowlist resolved under `data/runs/<id>/`; corrupt or partial JSON raises `StoreError`.
- Secret redaction at capture: store `secret_fingerprint`, never the value; test packet/logs/errors.
- Audit: canonical JSON, `prev_hash`, `hash`, append-only; per-run locks serialize append/status/decision updates; an atomically written `audit.checkpoint.json` (`count` + `head`) detects tail truncation, and verification rejects cross-run events, sequence gaps, and broken hashes. Verify command; label “tamper-evident local log, not non-repudiation.”
- Retention: `POST /api/runs/{id}/delete` removes run, draft, temp; no backups.
- Dependency lockfile, `pip-audit`, `ruff`; no network at runtime.
- No live tenant, no credentials, no third-party calls.

## Test vectors

- Zip: `../`, absolute path, empty/`.`, symlink, hardlink metadata, NUL, drive letter, encrypted entry, high ratio (small and large entries), per-entry/total size caps, many files.
- XML: external entity, billion laughs, DTD, XInclude.
- YAML: `!!`, `!python/...`, verbatim `!<...>`, recursive alias.
- XSS: PCF label, filename, JSON string, Gosu comment, packet.
- CSRF: missing/invalid token, query-string token, cross-origin, GET mutation.
- Session: unsigned/chosen cookie is replaced; signed cookie round-trips.
- Host/Origin: empty Host, wrong port, wrong scheme.
- Audit: edit/delete/reorder/truncate, cross-run copy, concurrent appends.
- Intake: symlink enumerated as unsupported, malformed JSON/YAML marked corrupt.
- Secrets: raw value absent from evidence, packet, logs, errors.
- Path traversal: artifact read outside run dir.
