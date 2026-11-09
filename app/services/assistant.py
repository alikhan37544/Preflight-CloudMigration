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


def _artifact_family(path: str) -> str:
    lower = path.lower().replace("\\", "/")
    if lower.endswith(".pcf"):
        return "PCF"
    if lower.endswith(".eti"):
        return "installed entity"
    if lower.endswith(".etx"):
        return "entity extension"
    if lower.endswith(".tti"):
        return "typelist"
    if lower.endswith(".ttx"):
        return "typelist extension"
    if "/template/" in lower or lower.startswith("product/template/"):
        return "APD template"
    if lower.startswith("gtest/") or "/gtest/" in lower:
        return "tests"
    if lower.endswith(".gs"):
        return "Gosu"
    if lower.endswith((".yaml", ".yml")):
        return "codegen/config YAML"
    if lower.endswith(".json"):
        return "JSON config"
    if lower.endswith(".xml"):
        return "XML config"
    return "other artefacts"


def _artifact_families(items: list[Evidence]) -> list[str]:
    ordered: list[str] = []
    for item in items:
        family = _artifact_family(item.path)
        if family not in ordered:
            ordered.append(family)
    return ordered


def _join_words(values: list[str]) -> str:
    if not values:
        return "none"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " and " + values[-1]


def _feature_evidence(feature, evidence: list[Evidence]) -> list[Evidence]:
    by_id = {item.evidence_id: item for item in evidence}
    return [by_id[eid] for eid in feature.evidence_ids if eid in by_id]


def _record_word(count: int) -> str:
    return "record" if count == 1 else "records"



def answer_question(question: str, discovery: DiscoveryResult, review: ReviewResult,
                    reconstruction: ReconstructionResult,
                    feature_id: str | None = None) -> AssistantAnswer:
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
        feature = (
            next((f for f in discovery.features if f.feature_id == feature_id), None)
            if feature_id else None
        )
        feature_evidence = set(feature.evidence_ids) if feature else None
        tests = [
            ev for ev in discovery.evidence
            if ("gtest/" in ev.path or "/gtest/" in ev.path)
            and (feature_evidence is None or ev.evidence_id in feature_evidence)
        ]
        scope = (
            f" linked to {feature.name} ({feature.feature_id})"
            if feature else " linked to the selected feature"
        )
        if tests:
            citations = _citations_from(tests)
            paths = {ev.path for ev in tests}
            unit_findings = [f for f in review.findings if f.rule_id == "PF-GW-GUNIT-001"]
            extra = (
                " A separate PF-GW-GUNIT-001 advisory finding flags DB-coupled test code."
                if unit_findings else ""
            )
            return AssistantAnswer(
                answer=(
                    f"{len(tests)} test evidence records across {len(paths)} file"
                    f"{'s' if len(paths) != 1 else ''}{scope}.{extra}"
                ),
                grounded=True,
                citations=citations,
                searched_scopes=["gtest", "feature evidence"],
            )
        if feature:
            return _refusal(
                f"no test evidence is linked to {feature.feature_id} in this snapshot.",
                searched=["gtest", "feature evidence"],
                missing=[f"a test artefact linked to {feature.name}"],
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
        feature = None
        if feature_id:
            feature = next((f for f in discovery.features if f.feature_id == feature_id), None)
        if feature is None:
            feature = next(
                (f for f in discovery.features
                 if f.feature_id == "PA-VEH-01"
                 or f.capability == "vehicle_information"),
                None,
            )
        if feature:
            items = _feature_evidence(feature, discovery.evidence)
            if not items:
                return _refusal(
                    f"no evidence record for {feature.feature_id} is present in this run.",
                    searched=["feature evidence", "spine"],
                    missing=[f"evidence linked to {feature.feature_id}"],
                )
            citations = _citations_from(items)
            paths = {ev.path for ev in items}
            families = _artifact_families(items)
            answer = (
                f"{feature.name} ({feature.feature_id}) is supported by {len(items)} evidence "
                f"{_record_word(len(items))} across {len(paths)} file"
                f"{'s' if len(paths) != 1 else ''}. Artefact families present: "
                f"{_join_words(families)}."
            )
            territory_gaps = [
                gap for gap in discovery.gaps
                if "territor" in gap.subject.lower()
            ]
            territory_assumptions = [
                item for item in reconstruction.assumptions
                if "territor" in item.statement.lower()
            ]
            if territory_gaps:
                answer += (
                    " The snapshot records a territory gap ("
                    + ", ".join(gap.gap_id for gap in territory_gaps)
                    + ") rather than inventing a rating source."
                )
            if territory_assumptions:
                answer += (
                    " The assumption register records "
                    f"{len(territory_assumptions)} territory assumption"
                    f"{'s' if len(territory_assumptions) != 1 else ''} ("
                    + ", ".join(item.assumption_id for item in territory_assumptions)
                    + ")."
                )
            return AssistantAnswer(
                answer=answer,
                grounded=True,
                citations=citations,
                searched_scopes=["feature evidence", "spine", "gaps", "assumptions"],
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
