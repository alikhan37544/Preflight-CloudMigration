"""Two synthetic insurer profiles for the code-migration demonstration.

Both estates are invented. The profiles are designed to exercise different
cloud-blocker mixes, not to represent any real insurer or Guidewire customer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings

CASE_STUDIES: dict[str, dict[str, Any]] = {
    "cascade-mutual": {
        "case_id": "cascade-mutual",
        "name": "Cascade Mutual",
        "segment": "Monoline Personal Auto mutual",
        "tagline": "A focused personal auto carrier with a dealer-feed integration and a small, high-risk custom rating surface.",
        "source_release": "Qusar 2026.08 (pre-cloud snapshot)",
        "target_release": "GWCP 2027.04",
        "cloud_program": "Cloud Retrofit without APD App · single LOB",
        "footprint": {
            "policies": "420,000",
            "states": "TX · OR · WA",
            "pcf_screens": "38",
            "custom_gosu_files": "64",
            "java_plugins": "3",
            "integrations": "7",
            "rating_calls_per_day": "1.8M",
        },
        "lobs": [
            {
                "name": "Personal Auto",
                "product_model": "CascadeAuto (custom, APD-targeted)",
                "editions": ["TX-Base", "OR-Base", "WA-Base"],
                "custom_features": [
                    "Telematics discount tier",
                    "Dealer vehicle feed",
                    "Agency commission publication",
                ],
            }
        ],
        "custom_features": [
            {
                "name": "Telematics discount tier",
                "owner": "Product & Rating",
                "description": "Reads a vendor rating table and applies a telematics tier before base rating.",
                "evidence_paths": [
                    "gsrc/cascade/rating/VehicleRatingQuery.gs",
                    "java/cascade/plugin/LegacyRatingPlugin.java",
                ],
                "anti_patterns": ["PF-CODE-SQL-001", "PF-CODE-SQL-002", "PF-CODE-MT-001"],
                "cloud_target": "Cloud Data Access read model + typed Gosu rating factor service",
            },
            {
                "name": "Dealer vehicle feed",
                "owner": "Distribution",
                "description": "A servlet receives dealer inventory and vehicle attributes from a partner portal.",
                "evidence_paths": ["gsrc/cascade/integration/DealerFeedServlet.gs"],
                "anti_patterns": ["PF-CODE-SRV-001"],
                "cloud_target": "Cloud API extension endpoint or Integration Gateway route",
            },
            {
                "name": "Agency commission publication",
                "owner": "Finance & Distribution",
                "description": "A legacy JMS message-transport plugin publishes policy-bound events to the commission system.",
                "evidence_paths": ["gsrc/cascade/integration/PolicyMessagingPlugin.gs"],
                "anti_patterns": ["PF-CODE-MSG-001"],
                "cloud_target": "App Events publication + Integration Gateway delivery",
            },
            {
                "name": "State rating cache",
                "owner": "Platform Engineering",
                "description": "Caches last tenant and rating factors in static fields for fast lookup.",
                "evidence_paths": ["gsrc/cascade/cache/RatingCache.gs"],
                "anti_patterns": ["PF-CODE-MT-001"],
                "cloud_target": "Tenant-scoped service state or managed cache",
            },
            {
                "name": "Vendor credential bootstrap",
                "owner": "Security",
                "description": "Vendor API credentials are initialized from literals in a Gosu configuration class.",
                "evidence_paths": ["gsrc/cascade/security/VendorCredentials.gs"],
                "anti_patterns": ["PF-CODE-SEC-001"],
                "cloud_target": "Cloud secret manager binding with rotation",
            },
        ],
        "constraints": [
            "Direct SQL is prohibited; reads move to Cloud Data Access and writes to application APIs.",
            "The dealer feed has a contractual 200 ms p95 acknowledgement budget.",
            "TX, OR, and WA maintain separate mandatory-offer and notice rules.",
            "The commission system cannot subscribe to App Events directly; it needs an Integration Gateway route.",
            "A state filing window prevents a long freeze on rating changes.",
        ],
        "expected_findings": [
            {"rule_id": "PF-CODE-SQL-001", "category": "data_access", "count": 3,
             "summary": "JDBC reads in a Gosu rating query and a Java plugin."},
            {"rule_id": "PF-CODE-SRV-001", "category": "servlet", "count": 1,
             "summary": "Dealer-feed servlet is not a supported cloud extension point."},
            {"rule_id": "PF-CODE-MSG-001", "category": "messaging", "count": 2,
             "summary": "JMS message-transport plugin and legacy messaging config."},
            {"rule_id": "PF-CODE-SEC-001", "category": "security", "count": 2,
             "summary": "Vendor API key and password literals in Gosu."},
            {"rule_id": "PF-CODE-MT-001", "category": "multitenancy", "count": 2,
             "summary": "Static rating cache and static tenant marker."},
            {"rule_id": "PF-CODE-APD-001", "category": "apd", "count": 1,
             "summary": "Long APD type name in the autogenerated product template."},
        ],
        "case_thesis": (
            "Cascade demonstrates the narrow, high-value case: one line of business, a "
            "small number of integration surfaces, and a rating path where direct SQL is "
            "both a cloud blocker and a latency risk. The green signal is meaningful only "
            "after the rating rewrite, the dealer-feed route, and the App Events publication "
            "are all reviewed by their owners."
        ),
    },
    "harbor-pc": {
        "case_id": "harbor-pc",
        "name": "Harbor P&C",
        "segment": "Multi-line regional P&C group",
        "tagline": "A complex personal and commercial carrier whose claims, billing, and coastal underwriting customizations cross three applications.",
        "source_release": "Qusar 2026.08 (pre-cloud snapshot)",
        "target_release": "GWCP 2027.04",
        "cloud_program": "Cloud Retrofit with APD conversion · multi-LOB",
        "footprint": {
            "policies": "2.6M",
            "states": "TX · LA · FL · WA",
            "pcf_screens": "214",
            "custom_gosu_files": "1,180",
            "java_plugins": "19",
            "integrations": "42",
            "rating_calls_per_day": "11.4M",
        },
        "lobs": [
            {
                "name": "Personal Auto",
                "product_model": "HarborAuto",
                "editions": ["TX-Base", "LA-Base", "FL-Base"],
                "custom_features": ["Telematics discount", "Windshield glass limit"],
            },
            {
                "name": "Homeowners",
                "product_model": "HarborHome (APD-targeted)",
                "editions": ["Coastal", "Inland"],
                "custom_features": ["Coastal wind mitigation", "Roof-age eligibility"],
            },
            {
                "name": "Workers' Compensation",
                "product_model": "HarborWC",
                "editions": ["TX-Base", "LA-Base"],
                "custom_features": ["Classification table integration", "Experience-mod publication"],
            },
        ],
        "custom_features": [
            {
                "name": "Coastal wind mitigation",
                "owner": "Homeowners Product",
                "description": "Combines dwelling attributes, mitigation credits, and a vendor wind model into an eligibility decision.",
                "evidence_paths": [
                    "gsrc/harbor/underwriting/CoastalEligibility.gs",
                    "product/template/HarborHomeTemplate.xml",
                ],
                "anti_patterns": ["PF-CODE-API-002", "PF-CODE-MT-001", "PF-CODE-APD-001"],
                "cloud_target": "Public API + tenant-scoped eligibility service + codegen override",
            },
            {
                "name": "Claims vendor gateway",
                "owner": "Claims Technology",
                "description": "A servlet forwards claim notices to a vendor and receives acknowledgements.",
                "evidence_paths": ["gsrc/harbor/integration/ClaimsGatewayServlet.gs"],
                "anti_patterns": ["PF-CODE-SRV-001"],
                "cloud_target": "Cloud API extension endpoint or Integration Gateway route",
            },
            {
                "name": "Vendor MQ publication",
                "owner": "Enterprise Integration",
                "description": "A message-transport plugin publishes claim and policy events to an on-premises MQ estate.",
                "evidence_paths": [
                    "gsrc/harbor/integration/VendorMqPublisher.gs",
                    "config/integration/messaging/vendor-mq.xml",
                ],
                "anti_patterns": ["PF-CODE-MSG-001"],
                "cloud_target": "App Events + Integration Gateway protocol bridge",
            },
            {
                "name": "Billing reconciliation batch",
                "owner": "Billing Operations",
                "description": "A nightly batch reads legacy billing tables, writes reconciliation files, and can exit the process on error.",
                "evidence_paths": ["gsrc/harbor/batch/BillingReconciliation.gs"],
                "anti_patterns": ["PF-CODE-SQL-001", "PF-CODE-MT-002"],
                "cloud_target": "Cloud API job + managed scheduler + Cloud Data Access read model",
            },
            {
                "name": "Experience-mod publication",
                "owner": "Workers' Comp Actuarial",
                "description": "Publishes experience-modification values through a legacy JMS transport.",
                "evidence_paths": ["gsrc/harbor/rating/WindRatingLookup.gs"],
                "anti_patterns": ["PF-CODE-SQL-001", "PF-CODE-SQL-002", "PF-CODE-MSG-001"],
                "cloud_target": "App Events publication + typed rating lookup",
            },
            {
                "name": "Vendor credentials and claim logs",
                "owner": "Security & Claims",
                "description": "Vendor credentials are embedded in code and claim identifiers are printed to standard output.",
                "evidence_paths": [
                    "gsrc/harbor/security/VendorSecrets.gs",
                    "gsrc/harbor/logging/ClaimLogger.gs",
                ],
                "anti_patterns": ["PF-CODE-SEC-001", "PF-CODE-LOG-001", "PF-CODE-SEC-002"],
                "cloud_target": "Cloud secret manager + structured redacted logging",
            },
        ],
        "constraints": [
            "Three LOBs share one Account but have different edition and eligibility rules.",
            "Claims and Billing customizations cross application boundaries.",
            "Coastal underwriting has a filed-model dependency and a state audit trail.",
            "The vendor MQ estate cannot be retired during the first cloud release.",
            "Workers' comp classification updates run under a regulatory calendar.",
            "APD conversion and code migration run in parallel, so type-name changes can invalidate endpoint drafts.",
        ],
        "expected_findings": [
            {"rule_id": "PF-CODE-SQL-001", "category": "data_access", "count": 5,
             "summary": "JDBC in rating, billing reconciliation, and Java plugins."},
            {"rule_id": "PF-CODE-SQL-002", "category": "data_access", "count": 2,
             "summary": "Concatenated SQL in rating and reconciliation paths."},
            {"rule_id": "PF-CODE-MSG-001", "category": "messaging", "count": 3,
             "summary": "JMS/MQ plugins and XML transport configuration."},
            {"rule_id": "PF-CODE-SRV-001", "category": "servlet", "count": 1,
             "summary": "Claims vendor servlet."},
            {"rule_id": "PF-CODE-API-002", "category": "api", "count": 2,
             "summary": "Internal Guidewire package references in underwriting."},
            {"rule_id": "PF-CODE-MT-001", "category": "multitenancy", "count": 3,
             "summary": "Static caches in underwriting and Java rating code."},
            {"rule_id": "PF-CODE-MT-002", "category": "multitenancy", "count": 2,
             "summary": "Thread, process-exit, and local-path assumptions in billing."},
            {"rule_id": "PF-CODE-SEC-001", "category": "security", "count": 2,
             "summary": "Vendor credential literals."},
            {"rule_id": "PF-CODE-SEC-002", "category": "security", "count": 1,
             "summary": "MD5 digest in a legacy Java rating plugin."},
            {"rule_id": "PF-CODE-APD-001", "category": "apd", "count": 1,
             "summary": "Long Homeowners APD type name."},
        ],
        "case_thesis": (
            "Harbor demonstrates the hard case: the code-level green signal is necessary but "
            "not sufficient. The Critic keeps architectural risks visible across applications, "
            "and the upgrade simulator shows why a green bundle must be invalidated when the "
            "target release changes an APD or App Events constraint mid-assessment."
        ),
    },
}


def list_case_studies() -> list[dict[str, Any]]:
    return [CASE_STUDIES[key] for key in CASE_STUDIES]


def get_case_study(case_id: str) -> dict[str, Any]:
    try:
        return CASE_STUDIES[case_id]
    except KeyError as exc:
        raise KeyError(f"unknown case study: {case_id}") from exc


def case_source_root(settings: Settings, case_id: str) -> Path:
    """Resolve a whitelisted case fixture without accepting user paths."""
    get_case_study(case_id)
    root = (settings.fixtures_dir / "case-studies" / case_id).resolve()
    fixtures = settings.fixtures_dir.resolve()
    if fixtures not in root.parents:
        raise ValueError("case fixture escapes the fixtures directory")
    if not root.is_dir():
        raise FileNotFoundError(f"case fixture not found: {case_id}")
    return root
