"""Reconstruction: apply mapping rules, write a local Cloud API extension draft.

The draft is a local, non-deployable proposal. ``_gen`` files are never
written or edited. Every change starts pending.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from app.models import (
    Assumption,
    Change,
    Confidence,
    Disposition,
    Evidence,
    Feature,
    Mapping,
    Provenance,
    Spine,
    SpineEdge,
    SpineNode,
)
from app.services.discovery import DiscoveryResult
from app.models import Manifest

SCHEMA = "config/integration/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json"
MAPPING = "config/integration/mappings/ext/policyperiod/v1/policyperiod_pa_ext-1.0.mapping.json"
UPDATER = "config/integration/updaters/ext/policyperiod/v1/policyperiod_pa_ext-1.0.updater.json"
CODEGEN = "config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml"
PRODUCT_ACCESS = "config/integration/apis/installedlobs/pa_ext-1.0.yaml"
DRAFT_FILES = (SCHEMA, MAPPING, UPDATER, CODEGEN, PRODUCT_ACCESS)

CODEGEN_URL = "https://docs.guidewire.com/cloud/pc/202603/cloudapica/cloudAPI/topics/508-LOBEndpoints/03-codegen-config-files/c_codegen_config_file_syntax.html"
COMPILE_URL = "https://docs.guidewire.com/cloud/is/202607/cloudapica/cloudAPI/LOBEndpoints/generating-LOB-endpoints/c_correcting_compile_errors.html"

CONTRACTS = Path(__file__).resolve().parents[2] / "templates" / "target" / "contracts.json"
MAPPING_RULES = Path(__file__).resolve().parents[2] / "rules" / "mapping_rules.yaml"


@dataclass
class ReconstructionResult:
    feature_id: str
    mappings: list[Mapping]
    changes: list[Change]
    assumptions: list[Assumption]
    draft_root: Path
    draft_files: dict[str, str]
    patch_diff: str
    spines: dict[str, Spine]
    validation_errors: list[str] = field(default_factory=list)
    silent_omissions: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _mapping(index: int, rule_id: str, source_ref: str, source_layer: str, target_path: str,
             target_name: str, disposition: Disposition, provenance: Provenance,
             rationale: str, confidence: Confidence = Confidence.LINKED,
             source_url: str | None = None, quote: str | None = None) -> Mapping:
    return Mapping(
        mapping_id=f"M-{index:02d}",
        source_ref=source_ref,
        source_name=source_ref.rsplit(".", 1)[-1],
        source_layer=source_layer,
        target_path=target_path,
        target_name=target_name,
        disposition=disposition,
        rule_id=rule_id,
        provenance=provenance,
        confidence=confidence,
        rationale=rationale,
        source_url=source_url,
        quote=quote,
    )


def _build_mappings() -> list[Mapping]:
    """Apply the canonical mapping rule pack; no mapping rows live in code."""
    payload = yaml.safe_load(MAPPING_RULES.read_text(encoding="utf-8")) or {}
    mappings: list[Mapping] = []
    for row in payload.get("rules", []):
        if not row.get("emitted", True):
            continue
        index = len(mappings) + 1
        rationale = row.get("rationale") or (
            "Documented codegen override from the public codegen config example."
            if row.get("provenance") == "guidewire-doc" else "PreFlight convention; reviewer approval required."
        )
        mappings.append(
            Mapping(
                mapping_id=f"M-{index:02d}",
                source_ref=row["source"],
                source_name=row["source"].rsplit(".", 1)[-1],
                source_layer=row["source_layer"],
                target_path=row["target"],
                target_name=row["target_name"],
                disposition=Disposition(row["disposition"]),
                rule_id=row["rule_id"],
                provenance=Provenance(row["provenance"]),
                confidence=Confidence.LINKED,
                rationale=rationale,
                source_url=row.get("source_url"),
                quote=row.get("quote"),
            )
        )
    return mappings

def _schema_document() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "preflight-target-v1",
        "title": "PreFlight local Cloud API extension draft (not official Guidewire schema)",
        "type": "object",
        "additionalProperties": False,
        # garageLocation is optional in the codegen draft
        # (GarageLocation.requiredForCreate: false), so it is not required here.
        "required": ["modelYear", "make", "vin", "usage", "vehicleType"],
        "properties": {
            "modelYear": {"type": "integer", "minimum": 1900, "maximum": 2100},
            "make": {"type": "string", "maxLength": 80},
            "vin": {"type": "string", "minLength": 11, "maxLength": 17},
            "usage": {"type": "string", "enum": ["pleasure", "commute", "business"]},
            "vehicleType": {"type": "string", "enum": ["passenger", "motorcycle", "trailer"]},
            "garageLocation": {"type": "string", "maxLength": 80},
        },
    }


def _mapping_document(mappings: list[Mapping]) -> dict:
    return {
        "schema_version": "1.0",
        "feature_id": "PA-VEH-01",
        "mappings": [
            {
                "source": m.source_ref,
                "source_layer": m.source_layer,
                "target": m.target_path,
                "disposition": m.disposition.value,
                "rule_id": m.rule_id,
                "provenance": m.provenance.value,
            }
            for m in mappings
        ],
    }


def _updater_document() -> dict:
    fields = {
        "modelYear": "ModelYear", "make": "Make", "vin": "VIN", "usage": "Usage",
        "vehicleType": "VehicleType", "garageLocation": "GarageLocation_Ext",
    }
    return {"schema_version": "1.0", "create": dict(fields), "update": dict(fields)}


def _codegen_document() -> dict:
    return {
        "schema_version": "1.0",
        "types": {
            "PAVehicle": {
                "nameOverride": "PersonalVehicle",
                "autonumber": "VehicleNumber",
                "toCreateAndAdd": "createAndAddVehicle",
                "toRemove": "removeVehicle",
                "fields": {
                    "Year": {"nameOverride": "ModelYear"},
                    # APD template field name -> installed extension field name.
                    # Optional here and in the schema; the updater maps the API
                    # property to GarageLocation_Ext.
                    "GarageLocation": {
                        "nameOverride": "GarageLocation_Ext",
                        "requiredForCreate": False,
                    },
                },
            },
            "PADriver": {"nameOverride": "VehicleDriver"},
            "PALine": {"nameOverride": "PersonalAutoLine"},
            "PersonalAutoRatingFactor": {"nameOverride": "PersonalAutoRatingFactorConfiguration"},
        },
        "wizardStepIds": False,
    }


def _product_access_document() -> dict:
    return {"schema_version": "1.0", "productCode": "pa", "productName": "PersonalAuto", "enabled": True}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _unified(rel: str, content: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            [], content.splitlines(), fromfile="/dev/null", tofile=f"b/{rel}", lineterm=""
        )
    )


def _add_spine_targets(spine: Spine, schema_rel: str, codegen_rel: str) -> Spine:
    nodes = list(spine.nodes)
    edges = list(spine.edges)
    node_ids = {node.id for node in nodes}

    def add_node(node: SpineNode) -> None:
        if node.id not in node_ids:
            node_ids.add(node.id)
            nodes.append(node)

    def add_edge(src: str, dst: str, kind: str) -> None:
        if src in node_ids and dst in node_ids:
            edges.append(SpineEdge(id=f"E-{len(edges) + 1:03d}", src=src, dst=dst, kind=kind,
                                   confidence=Confidence.LINKED))

    template_node = next((n for n in nodes if n.artifact_path and "/template/" in n.artifact_path), None)
    entity_node = next((n for n in nodes if n.artifact_path and n.artifact_path.endswith(".eti")), None)
    typelist_node = next((n for n in nodes if n.artifact_path and n.artifact_path.endswith(".ttx")), None)

    schema_id = f"schema:{schema_rel}"
    codegen_id = f"codegen:{codegen_rel}"
    add_node(SpineNode(id=schema_id, kind="config", label="PA extension schema",
                       artifact_path=schema_rel, confidence=Confidence.LINKED))
    add_node(SpineNode(id=codegen_id, kind="config", label="PA codegen config",
                       artifact_path=codegen_rel, confidence=Confidence.LINKED))

    if entity_node and typelist_node:
        add_edge(entity_node.id, schema_id, "configures")
        add_edge(typelist_node.id, schema_id, "configures")

    if template_node:
        for type_name in ["PAVehicle", "PAVehicle.Year", "PADriver", "PALine"]:
            type_id = f"codegen:{type_name}"
            add_node(SpineNode(id=type_id, kind="config", label=type_name,
                               artifact_path=codegen_rel, confidence=Confidence.LINKED))
            add_edge(template_node.id, type_id, "configures")

    return Spine(nodes=nodes, edges=edges, layout=spine.layout)


def _validate(draft_root: Path) -> list[str]:
    errors: list[str] = []
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))

    for rel in DRAFT_FILES:
        if not (draft_root / rel).is_file():
            errors.append(f"missing draft file: {rel}")

    for path in draft_root.rglob("*"):
        if path.is_file() and "_gen" in path.name:
            errors.append(f"generated file present in draft: {path.relative_to(draft_root)}")

    schema_path = draft_root / SCHEMA
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        if schema.get("$id") != "preflight-target-v1":
            errors.append("schema $id must be preflight-target-v1")
    except Exception as exc:
        errors.append(f"schema draft invalid: {exc}")

    mapping_path = draft_root / MAPPING
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        Draft202012Validator(contracts["mapping"]).validate(mapping)
    except Exception as exc:
        errors.append(f"mapping draft invalid: {exc}")

    updater_path = draft_root / UPDATER
    try:
        updater = json.loads(updater_path.read_text(encoding="utf-8"))
        Draft202012Validator(contracts["updater"]).validate(updater)
    except Exception as exc:
        errors.append(f"updater draft invalid: {exc}")

    codegen_path = draft_root / CODEGEN
    try:
        codegen = yaml.safe_load(codegen_path.read_text(encoding="utf-8"))
        if not isinstance(codegen.get("types"), dict) or not codegen["types"]:
            errors.append("codegen draft has no types")
    except Exception as exc:
        errors.append(f"codegen draft invalid: {exc}")

    access_path = draft_root / PRODUCT_ACCESS
    try:
        access = yaml.safe_load(access_path.read_text(encoding="utf-8"))
        Draft202012Validator(contracts["product_access"]).validate(access)
    except Exception as exc:
        errors.append(f"product access draft invalid: {exc}")

    return errors


def validate_draft_directory(draft_root: Path) -> list[str]:
    return _validate(Path(draft_root))


def reconstruct(root: Path, manifest: Manifest, discovery: DiscoveryResult, feature_id: str,
                *, store=None, run_id: str | None = None, draft_root: Path | None = None) -> ReconstructionResult:
    feature = next((f for f in discovery.features if f.feature_id == feature_id), None)
    if feature is None:
        raise KeyError(feature_id)

    mappings = _build_mappings()
    covered = {m.source_ref for m in mappings}
    expected = {
        "PersonalVehicle.ModelYear", "PersonalVehicle.Make", "PersonalVehicle.VIN",
        "PersonalVehicle.Usage", "PersonalVehicle.VehicleType",
        "PersonalVehicle.GarageLocation_Ext", "VehicleType.Motorcycle_Ext",
        "PAVehicle", "PAVehicle.Year", "PADriver", "PALine",
        "PersonalAutoRatingFactorConfiguration",
    }
    silent_omissions = sorted(expected - covered)

    if draft_root is None:
        if store is not None and run_id:
            draft_root = store.run_dir(run_id) / "draft"
        else:
            draft_root = root.parent / "draft"
    draft_root = Path(draft_root)

    schema_doc = _schema_document()
    mapping_doc = _mapping_document(mappings)
    updater_doc = _updater_document()
    codegen_doc = _codegen_document()
    access_doc = _product_access_document()

    _write_text(draft_root / SCHEMA, json.dumps(schema_doc, indent=2) + "\n")
    _write_text(draft_root / MAPPING, json.dumps(mapping_doc, indent=2) + "\n")
    _write_text(draft_root / UPDATER, json.dumps(updater_doc, indent=2) + "\n")
    _write_text(draft_root / CODEGEN, yaml.safe_dump(codegen_doc, sort_keys=False))
    _write_text(draft_root / PRODUCT_ACCESS, yaml.safe_dump(access_doc, sort_keys=False))

    draft_files = {rel: (draft_root / rel).read_text(encoding="utf-8") for rel in DRAFT_FILES}

    changes: list[Change] = []
    diffs: list[str] = []
    for index, rel in enumerate(DRAFT_FILES, start=1):
        diff = _unified(rel, draft_files[rel])
        diffs.append(diff)
        changes.append(
            Change(
                change_id=f"C-{index:02d}",
                target_path=rel,
                diff=diff,
                mapping_id=mappings[min(index - 1, len(mappings) - 1)].mapping_id,
                approval_state="pending",
            )
        )

    gaps = {gap.subject.lower(): gap for gap in discovery.gaps}
    assumptions = [
        Assumption(
            assumption_id="A-01",
            statement="Territory_Ext exists in the installed entity, but no rating or territory source artefact was found in this snapshot.",
            impact="high",
            impact_range_days=(3.0, 5.0),
            impact_basis="1 unresolved source field, 1 dependent API property, and a missing rating table; review buffer included.",
            impact_confidence="low",
            impact_caveat="Heuristic planning range; not a quote or measured productivity claim.",
            status="open",
            owner="unassigned",
            question_to_ask="Which rating table or service consumes Territory_Ext, and is it in scope for this Retrofit?",
            gap_id=gaps.get("territory").gap_id if gaps.get("territory") else None,
        ),
        Assumption(
            assumption_id="A-02",
            statement="Rating inputs were not in a supported export, so rating behaviour cannot be traced from this snapshot.",
            impact="medium",
            impact_range_days=(2.0, 3.0),
            impact_basis="1 unsupported input artefact; rating scope must be confirmed by the delivery team.",
            impact_confidence="low",
            impact_caveat="Heuristic planning range; not a quote or measured productivity claim.",
            status="open",
            owner="unassigned",
            question_to_ask="Can the team provide a supported rating input export before scope is agreed?",
            gap_id=gaps.get("rating inputs").gap_id if gaps.get("rating inputs") else None,
        ),
        Assumption(
            assumption_id="A-03",
            statement=(
                "The 37-character type PersonalAutoRatingFactorConfiguration appears in two files "
                "(product/template/LongTypeA.xml and config/resources/productmodel/PersonalAuto.xml), "
                "above APD's 24-character import limit. It is a PA-VEH-02 dependency outside "
                "PA-VEH-01's 11 references; the draft adds a nameOverride mapping the truncated "
                "visualized name to the installed name."
            ),
            impact="high",
            impact_range_days=(7.0, 9.0),
            impact_basis=(
                "Two files carry the long type (template and product model), with 0 tests; "
                "7-9 engineer-days is a heuristic for cross-artefact review and compile validation, "
                "not a count-derived estimate."
            ),
            impact_confidence="medium",
            impact_caveat="Heuristic planning range; not a quote or measured productivity claim.",
            status="open",
            owner="unassigned",
            question_to_ask=(
                "Who owns the template and product-model change, and can the nameOverride be "
                "validated on the target release?"
            ),
            related_mapping_id=mappings[4].mapping_id,
        ),
    ]

    spines = {}
    if feature_id in discovery.spines:
        spines[feature_id] = _add_spine_targets(discovery.spines[feature_id], SCHEMA, CODEGEN)

    result = ReconstructionResult(
        feature_id=feature_id,
        mappings=mappings,
        changes=changes,
        assumptions=assumptions,
        draft_root=draft_root,
        draft_files=draft_files,
        patch_diff="\n".join(diffs),
        spines=spines,
        silent_omissions=silent_omissions,
    )
    result.validation_errors = _validate(draft_root)

    if store is not None and run_id:
        store.write_artifact(run_id, "mappings.json", {
            "schema_version": "1.0",
            "feature_id": feature_id,
            "mappings": [m.model_dump(mode="json", by_alias=True) for m in mappings],
        })
        store.write_artifact(run_id, "changes.json", {
            "schema_version": "1.0",
            "changes": [c.model_dump(mode="json") for c in changes],
        })
        store.write_artifact(run_id, "assumptions.json", {
            "schema_version": "1.0",
            "assumptions": [a.model_dump(mode="json") for a in assumptions],
        })
        if spines:
            store.write_artifact(run_id, "spine.json", {
                "schema_version": "1.0",
                "spines": {key: value.model_dump(mode="json") for key, value in spines.items()},
            })
        store.write_artifact(run_id, "patch.diff", result.patch_diff)

    return result
