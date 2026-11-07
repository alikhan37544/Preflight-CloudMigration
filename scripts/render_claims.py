"""Regenerate the human-readable claims ledger from the canonical JSON."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JSON = REPO / "docs" / "claims-ledger.json"
MD = REPO / "docs" / "claims-ledger.md"

REJECTED = [
    ("`IS-INT-1268` exists", "No public evidence found; removed everywhere."),
    ("`IS-SEC-1332`, `IS-SEC-1008`, `IS-IMP-1017` used in MVP", "Not verified in this audit; not used. If later verified, add to ledger first."),
    ("PCF expansion varies across public sources", "Guidewire uses both “Page Configuration File(s)” and “Page Configuration Format” in public material; PreFlight uses “Page Configuration File(s)” and does not claim a canonical XSD."),
    ("APD type-name limit is 30 characters", "Incorrect; public docs say 24 for type names."),
    ("`IS-SEC-1289` is one of 18 rules", "It is the Gosu Secure Coding Standard document containing multiple rules."),
    ("`IS-INT-1335` is the custom-servlet standard", "It is “Use of Guidewire Integration Framework.”"),
    ("“No offline pre-check exists”", "Cannot prove absence; say “public docs do not describe an offline pre-bid evidence pack.”"),
    ("“6–8 weeks → 5 minutes”", "Not a valid equivalence; no measured baseline."),
    ("“160 sub-agents verified”", "No reproducible provenance."),
    ("“Six-figure surprises” / “priced assumption register”", "No cost data; use “estimate-moving” and “impact-rated.”"),
    ("APD product/edition JSON in a pre-APD estate", "Incoherent scenario; v5 uses legacy product-model XML."),
]


def render() -> str:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    lines = [
        "# PreFlight Claims Ledger", "",
        "**Canonical machine-readable ledger:** `docs/claims-ledger.json`. This Markdown is generated from it; do not edit by hand.", "",
        f"**Access date:** {data.get('access_date', '2026-11-07')}. **Status values:** " + ", ".join(data["status_enum"]) + ".", "",
        "| ID | Claim | Status | Source / quote | Falsifier | Consequence |",
        "|---|---|---|---|---|---|",
    ]
    for claim in data["claims"]:
        lines.append(
            f"| {claim['id']} | {claim['claim']} | {claim['status']} | "
            f"{claim['source_url']} — {claim['quote']} | {claim['falsifier']} | {claim['consequence']} |"
        )
    lines += ["", "## Rejected / not used", "", "| Claim | Why rejected |", "|---|---|"]
    lines += [f"| {claim} | {reason} |" for claim, reason in REJECTED]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    MD.write_text(render(), encoding="utf-8")
    print(f"wrote {MD}")
