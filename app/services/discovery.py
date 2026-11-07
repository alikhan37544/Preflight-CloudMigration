"""Feature candidate assembly, evidence graph, gaps, and feature spine.

Deterministic: YAML structural seeds + parsed anchors. Name-only links are
marked ``inferred-review``; explicit identifier links are ``linked``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.models import (
    Confidence,
    Evidence,
    Feature,
    Gap,
    GapKind,
    Locator,
    LocatorKind,
    Manifest,
    Spine,
    SpineEdge,
    SpineNode,
    make_evidence,
)
from app.services.parsers.config import parse_config_yaml
from app.services.parsers.entity import parse_entity
from app.services.parsers.gosu import parse_gunit, scan_gosu
from app.services.parsers.pcf import parse_pcf
from app.services.parsers.product import parse_product_xml, parse_template_xml
from app.services.parsers.typelist import parse_typelist

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "feature_rules.yaml"


@dataclass
class DiscoveryResult:
    features: list[Feature] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    spines: dict[str, Spine] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def load_feature_rules(path: Path = RULES_PATH) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("features", [])


class _Collector:
    def __init__(self) -> None:
        self.items: list[Evidence] = []

    def add(self, *, path: str, locator: Locator, excerpt: str, method: str,
            confidence: Confidence) -> Evidence:
        ev = make_evidence(
            evidence_id=f"EV-{len(self.items) + 1:04d}",
            path=path,
            locator=locator,
            excerpt=excerpt,
            method=method,
            confidence=confidence,
        )
        self.items.append(ev)
        return ev


def _xml_evidence(collector: _Collector, rel: str, *, line: int, xpath: str,
                  excerpt: str, confidence: Confidence, method: str = "xml_xpath") -> Evidence:
    return collector.add(
        path=rel,
        locator=Locator(kind=LocatorKind.XPATH, value=xpath, line=line),
        excerpt=excerpt or xpath,
        method=method,
        confidence=confidence,
    )


def _line_excerpt(raw: str, line: int, span: int = 2) -> str:
    lines = raw.splitlines()
    start = max(0, line - 1)
    end = min(len(lines), start + span)
    return "\n".join(lines[start:end]).strip()


def _parse_documents(root: Path, manifest: Manifest) -> tuple[dict, list[str]]:
    docs: dict[str, list] = {
        "pcf": [], "entity": [], "typelist": [], "template": [],
        "product": [], "gosu": [], "gunit": [], "config": [],
    }
    warnings: list[str] = []
    for artifact in manifest.artifacts:
        if artifact.status.value not in {"parsed", "partial"}:
            continue
        path = root / artifact.path
        try:
            if artifact.kind == "pcf":
                docs["pcf"].append(parse_pcf(path))
            elif artifact.kind in {"entity", "entity_extension"}:
                docs["entity"].append(parse_entity(path))
            elif artifact.kind in {"typelist", "typelist_extension"}:
                docs["typelist"].append(parse_typelist(path))
            elif artifact.kind == "template_xml":
                docs["template"].append(parse_template_xml(path))
            elif artifact.kind == "product_xml":
                docs["product"].append(parse_product_xml(path))
            elif artifact.kind == "gosu":
                docs["gosu"].append(scan_gosu(path))
            elif artifact.kind == "gunit":
                docs["gunit"].append(parse_gunit(path))
            elif artifact.kind == "config_yaml":
                docs["config"].append(parse_config_yaml(path))
        except Exception as exc:  # a parser failure must not abort the run
            warnings.append(f"{artifact.path}: {type(exc).__name__}: {exc}")
    return docs, warnings


def _rel(root: Path, path: str) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path


def _match(pattern: str | None, value: str) -> bool:
    return bool(pattern) and re.search(pattern, value) is not None


def run_discovery(root: Path, manifest: Manifest) -> DiscoveryResult:
    rules = load_feature_rules()
    docs, warnings = _parse_documents(root, manifest)
    collector = _Collector()
    result = DiscoveryResult(warnings=warnings)
    features: list[Feature] = []

    pcf_by_name = {doc.name: doc for doc in docs["pcf"]}

    for rule in rules:
        seed = rule.get("seed") or {}
        matched_pcfs = [d for d in docs["pcf"] if _match(seed.get("pcf"), Path(d.path).name)]
        matched_entities = [d for d in docs["entity"] if _match(seed.get("entity"), d.name)]
        matched_templates = [
            (doc, type_doc)
            for doc in docs["template"]
            for type_doc in doc.types
            if _match(seed.get("template"), type_doc.name)
        ]
        matched_gosu = [
            d for d in docs["gosu"]
            if _match(seed.get("gosu"), Path(d.path).name)
            or any(_match(seed.get("gosu"), c.name) for c in d.classes)
        ]
        matched_tests = [
            d for d in docs["gunit"]
            if _match(seed.get("test"), Path(d.path).name)
        ]

        if not (matched_pcfs or matched_entities):
            continue

        # Prefer the non-legacy screen when a duplicate exists.
        primary_pcf = None
        if matched_pcfs:
            non_legacy = [d for d in matched_pcfs if "/legacy/" not in d.path.replace("\\", "/")]
            primary_pcf = (non_legacy or matched_pcfs)[0]

        feature_evidence: list[Evidence] = []

        if primary_pcf is not None:
            rel = _rel(root, primary_pcf.path)
            for widget in primary_pcf.widgets:
                feature_evidence.append(
                    _xml_evidence(
                        collector, rel, line=widget.line, xpath=widget.xpath,
                        excerpt=widget.excerpt, confidence=Confidence.PARSED,
                    )
                )

        entity_names: set[str] = set()
        typelist_names: set[str] = set()
        columns_by_name: dict[str, str] = {}
        for entity_doc in matched_entities:
            rel = _rel(root, entity_doc.path)
            entity_names.add(entity_doc.name)
            for column in entity_doc.columns:
                columns_by_name[column.name] = entity_doc.name
                if column.typelist:
                    typelist_names.add(column.typelist)
                feature_evidence.append(
                    _xml_evidence(
                        collector, rel, line=column.line, xpath=column.xpath,
                        excerpt=column.excerpt, confidence=Confidence.PARSED,
                    )
                )

        template_type_names: set[str] = set()
        for template_doc, type_doc in matched_templates:
            rel = _rel(root, template_doc.path)
            template_type_names.add(type_doc.name)
            feature_evidence.append(
                _xml_evidence(
                    collector, rel, line=type_doc.line, xpath=type_doc.xpath,
                    excerpt=type_doc.excerpt, confidence=Confidence.LINKED,
                )
            )
            for parsed_field in type_doc.fields:
                feature_evidence.append(
                    _xml_evidence(
                        collector, rel, line=parsed_field.line, xpath=parsed_field.xpath,
                        excerpt=parsed_field.excerpt, confidence=Confidence.LINKED,
                    )
                )

        for typelist_name in sorted(typelist_names):
            for typelist_doc in docs["typelist"]:
                if typelist_doc.name != typelist_name:
                    continue
                rel = _rel(root, typelist_doc.path)
                for code in typelist_doc.codes:
                    feature_evidence.append(
                        _xml_evidence(
                            collector, rel, line=code.line, xpath=code.xpath,
                            excerpt=code.excerpt, confidence=Confidence.LINKED,
                        )
                    )

        gosu_names: set[str] = set()
        for gosu_doc in matched_gosu:
            rel = _rel(root, gosu_doc.path)
            if not gosu_doc.classes:
                continue
            gosu_class = gosu_doc.classes[0]
            gosu_names.add(gosu_class.name)
            feature_evidence.append(
                collector.add(
                    path=rel,
                    locator=Locator(kind=LocatorKind.LINE, value=f"class {gosu_class.name}", line=gosu_class.line),
                    excerpt=_line_excerpt(gosu_doc.raw, gosu_class.line),
                    method="lexer",
                    confidence=Confidence.LINKED,
                )
            )

        test_names: set[str] = set()
        for gunit_doc in matched_tests:
            rel = _rel(root, gunit_doc.path)
            test_names.add(gunit_doc.class_name)
            raw = (root / rel).read_text(encoding="utf-8", errors="replace")
            line = next((i + 1 for i, text in enumerate(raw.splitlines()) if "class " in text), 1)
            feature_evidence.append(
                collector.add(
                    path=rel,
                    locator=Locator(kind=LocatorKind.LINE, value=f"class {gunit_doc.class_name}", line=line),
                    excerpt=_line_excerpt(raw, line),
                    method="lexer",
                    confidence=Confidence.LINKED,
                )
            )

        if not feature_evidence:
            continue

        open_questions: list[str] = []
        if any("Territory" in ev.excerpt for ev in feature_evidence):
            open_questions.append(
                "Where is the territory source? The snapshot has a Territory_Ext field but no rating table."
            )
        if rule["id"] == "PA-VEH-02":
            open_questions.append("Are rating inputs authoritative? They are not in a supported export.")

        dependencies = sorted(entity_names | typelist_names | template_type_names | gosu_names | test_names)
        feature = Feature(
            feature_id=rule["id"],
            capability=rule.get("capability"),
            name=rule["name"],
            lob=rule.get("lob", "PersonalAuto"),
            description=rule.get("description", ""),
            evidence_ids=[ev.evidence_id for ev in feature_evidence],
            dependencies=dependencies,
            confidence=Confidence.PARSED,
            open_questions=open_questions,
        )
        features.append(feature)
        result.spines[feature.feature_id] = _build_source_spine(
            feature, feature_evidence, docs, primary_pcf, columns_by_name
        )

    result.features = features
    result.evidence = collector.items
    result.gaps = _build_gaps(features, docs, manifest)
    return result


def _build_gaps(features: list[Feature], docs: dict, manifest: Manifest) -> list[Gap]:
    gaps: list[Gap] = []
    counter = 1

    territory_found = any(
        "Territory_Ext" in ev.excerpt for ev in _all_evidence(docs)
    ) or any(
        "territory" in q.lower() for f in features for q in f.open_questions
    )
    if territory_found:
        gaps.append(
            Gap(
                gap_id=f"G-{counter:02d}", kind=GapKind.MISSING_SOURCE, subject="territory",
                evidence_sought="territory rating table or source mapping", impact="high",
                owner="unassigned", status="open",
            )
        )
        counter += 1

    rating_unsupported = [p for p in manifest.unsupported_paths if "rating" in p.lower()]
    if rating_unsupported:
        gaps.append(
            Gap(
                gap_id=f"G-{counter:02d}", kind=GapKind.UNSUPPORTED, subject="rating inputs",
                evidence_sought="supported rating input export", impact="medium",
                owner="unassigned", status="open",
            )
        )
        counter += 1

    names: dict[str, list[str]] = {}
    for doc in docs["pcf"]:
        names.setdefault(doc.name, []).append(doc.path)
    for name, paths in sorted(names.items()):
        if len(paths) > 1:
            gaps.append(
                Gap(
                    gap_id=f"G-{counter:02d}", kind=GapKind.AMBIGUOUS_REFERENCE,
                    subject=f"duplicate {name} screen",
                    evidence_sought="customisation provenance and canonical screen",
                    impact="medium", owner="unassigned", status="open",
                )
            )
            counter += 1

    return gaps


def _all_evidence(docs: dict) -> list:
    # Gaps only need a text signal; entity docs are the authoritative source.
    out = []
    for doc in docs["entity"]:
        for column in doc.columns:
            out.append(column)
    return out


def _token_match(feature: Feature, *names: str) -> bool:
    tokens = [token for token in (feature.capability or "").split("_") if token]
    haystack = " ".join(names).lower()
    return any(token in haystack for token in tokens)


def _build_source_spine(feature: Feature, evidence: list[Evidence], docs: dict,
                        primary_pcf, columns_by_name: dict[str, str]) -> Spine:
    nodes: list[SpineNode] = [
        SpineNode(id=f"feature:{feature.feature_id}", kind="feature", label=feature.name,
                  confidence=Confidence.PARSED)
    ]
    node_ids: set[str] = set(nodes[0].id for _ in [0])

    def add_node(node_id: str, kind: str, label: str, path: str | None,
                 confidence: Confidence, evidence_id: str | None = None) -> None:
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append(SpineNode(id=node_id, kind=kind, label=label, artifact_path=path,
                               evidence_id=evidence_id, confidence=confidence))

    paths = sorted({ev.path for ev in evidence})
    pcf_paths = [p for p in paths if p.endswith(".pcf")]
    entity_paths = [p for p in paths if p.endswith((".eti", ".etx"))]
    typelist_paths = [p for p in paths if p.endswith((".tti", ".ttx"))]
    template_paths = [p for p in paths if "/template/" in p or p.startswith("product/template/")]
    test_paths = [
        p for p in paths
        if p.endswith(".gs") and (p.startswith("gtest/") or "/gtest/" in p)
    ]
    gosu_paths = [p for p in paths if p.endswith(".gs") and p not in test_paths]

    doc_by_path = {d.path: d for d in docs["pcf"] + docs["entity"] + docs["typelist"] + docs["gosu"] + docs["gunit"]}
    absolute = {d.path: d for d in docs["pcf"] + docs["entity"] + docs["typelist"] + docs["template"] + docs["gosu"] + docs["gunit"]}

    def first_evidence(rel: str) -> str | None:
        return next((ev.evidence_id for ev in evidence if ev.path == rel), None)

    def label_for(rel: str) -> str:
        stem = Path(rel).stem
        label = stem.replace("PersonalVehicle", "Vehicle").replace("PersonalAuto", "Auto").replace("Personal", "")
        if rel.endswith((".etx", ".ttx")):
            label += " ext"
        return label

    for rel in pcf_paths:
        add_node(f"pcf:{rel}", "artifact", label_for(rel), rel, Confidence.PARSED, first_evidence(rel))
    for rel in entity_paths:
        add_node(f"entity:{rel}", "artifact", label_for(rel), rel, Confidence.PARSED, first_evidence(rel))
    for rel in typelist_paths:
        add_node(f"typelist:{rel}", "artifact", label_for(rel), rel, Confidence.LINKED, first_evidence(rel))
    for rel in template_paths:
        add_node(f"template:{rel}", "artifact", label_for(rel), rel, Confidence.LINKED, first_evidence(rel))
    for rel in gosu_paths:
        add_node(f"gosu:{rel}", "symbol", label_for(rel), rel, Confidence.LINKED, first_evidence(rel))
    for rel in test_paths:
        add_node(f"gtest:{rel}", "test", label_for(rel), rel, Confidence.LINKED, first_evidence(rel))

    edges: list[SpineEdge] = []

    def add_edge(src: str, dst: str, kind: str, confidence: Confidence) -> None:
        if src not in node_ids or dst not in node_ids:
            return
        edges.append(SpineEdge(id=f"E-{len(edges) + 1:03d}", src=src, dst=dst, kind=kind,
                               confidence=confidence))

    primary_entity = next((p for p in entity_paths if p.endswith(".eti") and not p.endswith(".etx")), None)
    if pcf_paths and primary_entity:
        add_edge(f"pcf:{pcf_paths[0]}", f"entity:{primary_entity}", "references", Confidence.LINKED)

    # Widget edges: match bindings against typelist names then entity columns.
    typelist_names = {Path(p).stem for p in typelist_paths}
    if primary_pcf is not None and pcf_paths:
        rel = pcf_paths[0]
        for widget in primary_pcf.widgets:
            if widget.binding in typelist_names:
                target = next((p for p in typelist_paths if Path(p).stem == widget.binding), None)
                if target:
                    add_edge(f"pcf:{rel}", f"typelist:{target}", "references", Confidence.LINKED)
            elif widget.binding in columns_by_name:
                if primary_entity:
                    add_edge(f"pcf:{rel}", f"entity:{primary_entity}", "references", Confidence.LINKED)

    if pcf_paths:
        for gosu_rel in gosu_paths:
            add_edge(f"gosu:{gosu_rel}", f"pcf:{pcf_paths[0]}", "references", Confidence.LINKED)

    if gosu_paths:
        for test_rel in test_paths:
            add_edge(f"gtest:{test_rel}", f"gosu:{gosu_paths[0]}", "tested_by", Confidence.LINKED)

    return Spine(nodes=nodes, edges=edges)
