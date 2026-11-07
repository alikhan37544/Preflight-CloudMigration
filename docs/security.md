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
| Audit log | Tampering | Hash chain; `preflight verify-audit` |
| Browser session | CSRF, XSS | CSRF token; SameSite=Strict; autoescape; CSP |

## Controls

- CSRF synchronizer token per session, validated on every mutating POST; rotation on session change.
- Host/Origin allowlist; reject cross-origin mutations.
- CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`.
- Jinja2 autoescape; no `|safe`; JS uses `textContent`.
- Zip limits: 20,000 files, 500 MB compressed, 2 GB uncompressed, 100:1 ratio; reject encrypted entries, symlinks, absolute paths, `..`, NUL, drive letters.
- XML: `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`.
- YAML: `safe_load`; no arbitrary tags.
- Artifact reads: allowlist resolved under `data/runs/<id>/`.
- Secret redaction at capture: store `secret_fingerprint`, never the value; test packet/logs/errors.
- Audit: canonical JSON, `prev_hash`, `hash`, append-only; verify command; label “tamper-evident local log, not non-repudiation.”
- Retention: `POST /api/runs/{id}/delete` removes run, draft, temp; no backups.
- Dependency lockfile, `pip-audit`, `ruff`; no network at runtime.
- No live tenant, no credentials, no third-party calls.

## Test vectors

- Zip: `../`, absolute path, symlink, hardlink, NUL, drive letter, encrypted entry, high ratio, many files.
- XML: external entity, billion laughs, DTD, XInclude.
- YAML: arbitrary tag, recursive alias.
- XSS: PCF label, filename, JSON string, Gosu comment, packet.
- CSRF: missing/invalid token, cross-origin, GET mutation.
- Audit: edit/delete/reorder/truncate.
- Secrets: raw value absent from evidence, packet, logs, errors.
- Path traversal: artifact read outside run dir.
