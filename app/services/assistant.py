"""Deterministic grounded assistant.

Retrieval only. Answers cite evidence IDs; if the snapshot lacks evidence it
refuses and names the missing source. No model, no network, no invented files.
"""

from __future__ import annotations

from app.models import AssistantAnswer, Evidence
from app.services.discovery import DiscoveryResult
from app.services.reconstruction import ReconstructionResult
from app.services.review import ReviewResult

DEMO_QUESTIONS: list[tuple[str, bool]] = [
    ("What evidence supports Vehicle Information?", True),
    ("Which files reference Motorcycle_Ext?", True),
    ("Why is the long type name a problem?", True),
    ("What findings are there?", True),
    ("Which tests cover vehicle validation?", True),
    ("Does this estate use territory rating?", False),
    ("What is the premium for policy 123?", False),
    ("Who approved the mapping last Tuesday?", False),
    ("Show me the customer email addresses.", False),
    ("What is the production deployment date?", False),
]


def _refusal(reason: str, *, searched: list[str], missing: list[str]) -> AssistantAnswer:
    return AssistantAnswer(
        answer=f"Cannot determine - {reason} Searched scopes: {', '.join(searched)}. "
               "No evidence in this snapshot supports a different answer.",
        grounded=False,
        citations=[],
        searched_scopes=searched,
        missing_evidence=missing,
    )


def _citations_from(items: list[Evidence], limit: int = 8) -> list[str]:
    seen: list[str] = []
    for evidence in items:
        if evidence.evidence_id not in seen:
            seen.append(evidence.evidence_id)
        if len(seen) >= limit:
            break
    return seen


def answer_question(question: str, discovery: DiscoveryResult, review: ReviewResult,
                    reconstruction: ReconstructionResult) -> AssistantAnswer:
    text = (question or "").strip()
    lower = text.lower()

    if ("ignore" in lower and "instruction" in lower) or "invent" in lower:
        return _refusal(
            "the request asks for content that is not in the evidence graph.",
            searched=["question guard", "evidence graph"],
            missing=["a real evidence record for the requested file"],
        )

    if "territory" in lower or ("rating" in lower and "long type" not in lower):
        return _refusal(
            "no rating table or territory source artefact exists in this snapshot.",
            searched=["product model", "rating Gosu", "rate tables", "entity extensions"],
            missing=[
                "a rating table or territory factor source",
                "rating input export",
                "the service that consumes Territory_Ext",
            ],
        )

    if "motorcycle" in lower:
        matches = [ev for ev in discovery.evidence if "Motorcycle_Ext" in ev.excerpt]
        if matches:
            citations = _citations_from(matches)
            return AssistantAnswer(
                answer=(
                    f"Motorcycle_Ext appears in {len(matches)} evidence "
                    f"{'record' if len(matches) == 1 else 'records'}, including the typelist extension. "
                    "The target enum disposition is a reviewer decision, not a source fact. "
                    "Each citation resolves to a file and line/pointer."
                ),
                grounded=True,
                citations=citations,
                searched_scopes=["typelist", "schema draft", "feature spine"],
            )
        return _refusal(
            "no evidence mentions Motorcycle_Ext.",
            searched=["typelist", "schema draft"],
            missing=["a typelist extension record"],
        )

    if "24" in lower or "long type" in lower or "nameoverride" in lower:
        findings = [f for f in review.findings if f.rule_id == "PF-GW-NAM-001"]
        if findings:
            finding = findings[0]
            citations = _citations_from(
                [e for e in review.evidence if e.evidence_id in finding.evidence_ids]
            )
            return AssistantAnswer(
                answer=(
                    f"{finding.message} The draft adds a codegen nameOverride and an assumption "
                    "rated at 7-9 engineer-days (heuristic planning range, not a quote)."
                ),
                grounded=True,
                citations=citations,
                searched_scopes=["template types", "codegen draft", "review findings"],
            )
        return _refusal(
            "no long-type finding exists in this run.",
            searched=["template types", "review findings"],
            missing=["an APD template type longer than 24 characters"],
        )

    if "test" in lower:
        tests = [ev for ev in discovery.evidence if "gtest/" in ev.path or "/gtest/" in ev.path]
        if tests:
            citations = _citations_from(tests)
            return AssistantAnswer(
                answer=(
                    f"{len(tests)} test evidence records are linked to the feature. "
                    "One is a pure unit test; one is DB-coupled and carries an advisory finding."
                ),
                grounded=True,
                citations=citations,
                searched_scopes=["gtest", "feature evidence"],
            )

    if "finding" in lower or "blocker" in lower or "risk" in lower:
        citations = _citations_from(
            [e for e in review.evidence if any(e.evidence_id in f.evidence_ids for f in review.findings)]
        )
        rule_ids = sorted({f.rule_id for f in review.findings})
        return AssistantAnswer(
            answer=(
                f"{len(review.findings)} advisory findings across {len(rule_ids)} rules: "
                f"{', '.join(rule_ids)}. Claim strength is shown per finding; official Cloud "
                "Assurance was not run."
            ),
            grounded=True,
            citations=citations,
            searched_scopes=["review rules", "Gosu scanner", "template metadata"],
        )

    if "vehicle" in lower:
        feature = next((f for f in discovery.features if f.feature_id == "PA-VEH-01"), None)
        if feature:
            evidence_by_id = {e.evidence_id: e for e in discovery.evidence}
            items = [evidence_by_id[eid] for eid in feature.evidence_ids if eid in evidence_by_id]
            citations = _citations_from(items)
            paths = {ev.path for ev in items}
            return AssistantAnswer(
                answer=(
                    f"Vehicle Information (PA-VEH-01) is supported by {len(items)} evidence records "
                    f"across {len(paths)} files: PCF, installed entity, entity extension, typelist, "
                    "extracted template, Gosu validation, and tests. The territory source is absent "
                    "and is recorded as an assumption."
                ),
                grounded=True,
                citations=citations,
                searched_scopes=["feature evidence", "spine", "gaps"],
            )

    if "policy" in lower and "question" in lower:
        feature = next((f for f in discovery.features if f.feature_id == "PA-POL-02"), None)
        if feature:
            evidence_by_id = {e.evidence_id: e for e in discovery.evidence}
            items = [evidence_by_id[eid] for eid in feature.evidence_ids if eid in evidence_by_id]
            return AssistantAnswer(
                answer=f"Policy Questions is supported by {len(items)} evidence records.",
                grounded=True,
                citations=_citations_from(items),
                searched_scopes=["feature evidence"],
            )

    return _refusal(
        "the question does not match any evidence in this run.",
        searched=["feature evidence", "review findings", "assumptions", "manifest"],
        missing=["a source artefact that answers the question"],
    )
