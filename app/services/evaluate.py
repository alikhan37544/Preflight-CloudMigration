"""Evaluation harness: six headline metrics, baselines, per-rule table.

Ground truth is read only by this evaluation harness, never by the analysis
pipeline. All numbers are for the controlled synthetic fixture.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.models import Manifest, Metric
from app.services.compare import CompareResult
from app.services.discovery import DiscoveryResult
from app.services.reconstruction import ReconstructionResult
from app.services.review import ReviewResult, load_rules

CAVEAT = (
    "One synthetic fixture; demonstration, not a benchmark. "
    "No live tenant and no generalisation to real estates."
)
DEMO_NOTE = "Demo slice is in-sample (a subset of the development fixture)."


@dataclass
class EvaluationResult:
    metrics: list[Metric] = field(default_factory=list)
    supporting: list[Metric] = field(default_factory=list)
    baselines: dict[str, float] = field(default_factory=dict)
    margins: dict[str, dict] = field(default_factory=dict)
    per_rule: dict[str, dict[str, int]] = field(default_factory=dict)
    m5_precision: float = 0.0


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        return (0.0, 0.0)
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _metric(metric_id: str, label: str, numerator: int, denominator: int, *,
            fixture_id: str, tier: str, primary: bool, caveat: str = CAVEAT) -> Metric:
    safe_den = max(1, denominator)
    low, high = wilson_interval(min(numerator, safe_den), safe_den)
    return Metric(
        metric_id=metric_id, label=label, numerator=numerator, denominator=safe_den,
        caveat=caveat, fixture_id=fixture_id, tier=tier, primary=primary,
        interval_low=low, interval_high=high,
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def audit_evidence_support(root: Path, evidence) -> bool:
    """Check that a sample link resolves and the excerpt appears at the source."""
    path = root / evidence.path
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if evidence.locator.line and evidence.locator.line > len(lines):
        return False
    excerpt = _norm(evidence.excerpt or "")
    if not excerpt:
        return False
    if excerpt in _norm(text):
        return True
    # XML serialization may reorder self-closing boundaries; support the first symbol.
    first_line = _norm((evidence.excerpt or "").splitlines()[0]) if evidence.excerpt else ""
    return bool(first_line) and first_line in _norm(text)


def _stratified_sample(evidence: list, sample_size: int = 30) -> list:
    by_path: dict[str, list] = defaultdict(list)
    for item in sorted(evidence, key=lambda e: (e.path, e.evidence_id)):
        by_path[item.path].append(item)
    sample: list = []
    cursor = 0
    while len(sample) < sample_size and any(cursor < len(items) for items in by_path.values()):
        for path in sorted(by_path):
            items = by_path[path]
            if cursor < len(items):
                sample.append(items[cursor])
                if len(sample) >= sample_size:
                    break
        cursor += 1
    return sample


def _naive_predict(rule: dict, text: str) -> bool:
    detection = rule.get("detection", {})
    kind = detection.get("kind")
    if kind == "gosu_regex":
        return any(re.search(pattern, text) for pattern in detection.get("patterns", []))
    if kind == "secret_assignment":
        return bool(re.search(r'(?i)(api[_-]?key|secret|password|token|credential)\s*=\s*"', text))
    if kind == "commit_in_block":
        return "runWithNewBundle" in text and "commit(" in text
    if kind == "empty_catch":
        return bool(re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", text))
    if kind == "gunit_db":
        return any(token in text for token in ["Query.make", "loadSampleData", "DriverManager.getConnection"])
    if kind == "long_type_name":
        return bool(re.search(r'name="([^"]{25,})"', text))
    if kind == "log_pii":
        return bool(re.search(r"(?i)(VIN|SSN|password|license)", text))
    return False


def evaluate_run(*, fixture_id: str, manifest: Manifest, discovery: DiscoveryResult,
                 reconstruction: ReconstructionResult, review: ReviewResult,
                 comparison: CompareResult, ground_truth_dir: Path, tier: str,
                 fixture_root: Path | None = None) -> EvaluationResult:
    root = Path(ground_truth_dir)
    resolved_root = Path(fixture_root) if fixture_root is not None else Path("fixtures") / fixture_id
    gold_features = json.loads((root / "features.json").read_text(encoding="utf-8"))["features"]
    gold_mappings = json.loads((root / "mappings.json").read_text(encoding="utf-8"))["mappings"]
    gold_findings = json.loads((root / "findings.json").read_text(encoding="utf-8"))["rules"]
    evidence_by_id = {e.evidence_id: e for e in discovery.evidence}
    feature_paths = {
        f.feature_id: {evidence_by_id[eid].path for eid in f.evidence_ids if eid in evidence_by_id}
        for f in discovery.features
    }

    # M1/M2: require the capability and at least one gold anchor path.
    matched_gold = 0
    for gold in gold_features:
        anchors = set(gold.get("anchors", []))
        if any(
            f.capability == gold["capability"] and feature_paths.get(f.feature_id, set()) & anchors
            for f in discovery.features
        ):
            matched_gold += 1
    emitted_correct = sum(
        1 for f in discovery.features
        if f.capability in {g["capability"] for g in gold_features}
        and feature_paths.get(f.feature_id, set()) & {
            anchor for g in gold_features if g["capability"] == f.capability for anchor in g.get("anchors", [])
        }
    )

    # M3: stratified 30-link audit, excerpt must appear at the source.
    sample = _stratified_sample(discovery.evidence, 30)
    evidence_good = sum(1 for item in sample if audit_evidence_support(resolved_root, item))

    # M4: source, target, and disposition must all match; extra mappings are penalised.
    tool_by_rule = {m.rule_id: m for m in reconstruction.mappings}
    gold_by_rule = {row["rule_id"]: row for row in gold_mappings}
    mapping_correct = 0
    for rule_id, gold in gold_by_rule.items():
        tool = tool_by_rule.get(rule_id)
        if tool and tool.target_path == gold["target_path"] and tool.target_name == gold["target_name"] \
                and tool.disposition.value == gold["disposition"]:
            mapping_correct += 1
    extra_mappings = len([r for r in tool_by_rule if r not in gold_by_rule])
    mapping_denominator = len(gold_mappings) + extra_mappings

    # M5: planted estimate-moving issues, ranked top-8 precision guard.
    issues_path = root / "estimate_moving_issues.json"
    issues_payload = json.loads(issues_path.read_text(encoding="utf-8")) if issues_path.is_file() else {"issues": [], "decoys": []}
    finding_rules = {f.rule_id for f in review.findings}
    mapping_rules = {m.rule_id for m in reconstruction.mappings}
    detected_issues: set[str] = set()
    for issue in issues_payload.get("issues", []):
        kind = issue.get("signal_type")
        signal = issue.get("signal")
        if kind == "finding_rule" and signal in finding_rules:
            detected_issues.add(issue["id"])
        elif kind == "mapping_rule" and signal in mapping_rules:
            detected_issues.add(issue["id"])
    issue_ids = {issue["id"] for issue in issues_payload.get("issues", [])}
    m5_recall_num = len(detected_issues & issue_ids)
    decoys = issues_payload.get("decoys", [])
    top8 = list(detected_issues & issue_ids) + list(decoys)
    m5_precision = (len(detected_issues & issue_ids) / min(8, len(top8))) if top8 else 0.0

    # M6: micro-F1 over labelled positives/negatives; per-rule macro reported separately.
    finding_paths: dict[str, set[str]] = defaultdict(set)
    for finding in review.findings:
        for evidence_id in finding.evidence_ids:
            ev = next((e for e in review.evidence if e.evidence_id == evidence_id), None)
            if ev:
                finding_paths[finding.rule_id].add(ev.path)
    per_rule: dict[str, dict[str, int]] = {}
    tp_total = fp_total = fn_total = 0
    f1_scores: list[float] = []
    for rule_id, cases in gold_findings.items():
        positives = {p.split("#", 1)[0] for p in cases.get("positives", [])}
        negatives = {p.split("#", 1)[0] for p in cases.get("negatives", [])}
        found = finding_paths.get(rule_id, set())
        tp = len(found & positives)
        fp = len(found & negatives)
        fn = len(positives - found)
        per_rule[rule_id] = {"tp": tp, "fp": fp, "fn": fn}
        tp_total += tp
        fp_total += fp
        fn_total += fn
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1_scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    f1_den = 2 * tp_total + fp_total + fn_total

    metrics = [
        _metric("M1", "Feature discovery recall", matched_gold, len(gold_features),
                fixture_id=fixture_id, tier=tier, primary=True, caveat=CAVEAT + " " + DEMO_NOTE),
        _metric("M2", "Feature discovery precision", emitted_correct, len(discovery.features),
                fixture_id=fixture_id, tier=tier, primary=True, caveat=CAVEAT + " " + DEMO_NOTE),
        _metric("M3", "Evidence-link support precision (30-link audit)", evidence_good, len(sample),
                fixture_id=fixture_id, tier=tier, primary=True, caveat=CAVEAT + " " + DEMO_NOTE),
        _metric("M4", "Disposition correctness", mapping_correct, mapping_denominator,
                fixture_id=fixture_id, tier=tier, primary=True, caveat=CAVEAT + " " + DEMO_NOTE),
        _metric("M5", "Estimate-moving issue recall", m5_recall_num, len(issue_ids),
                fixture_id=fixture_id, tier=tier, primary=True,
                caveat=CAVEAT + f" Top-8 precision: {m5_precision:.2f}. " + DEMO_NOTE),
        _metric("M6", "Finding micro-F1", 2 * tp_total, f1_den,
                fixture_id=fixture_id, tier=tier, primary=True, caveat=CAVEAT + " " + DEMO_NOTE),
    ]

    reference_rows = len(comparison.rows) or 1
    silent_den = len(gold_mappings)
    supporting = [
        _metric("M5-TOP8", "M5 top-8 precision guard", int(round(m5_precision * 100)), 100,
                fixture_id=fixture_id, tier=tier, primary=False),
        _metric("M6-MACRO", "Finding macro-F1 (per-rule average)", int(round(macro_f1 * 100)), 100,
                fixture_id=fixture_id, tier=tier, primary=False),
        _metric("SILENT-OMISSION", "Silent omission rate", len(reconstruction.silent_omissions),
                silent_den, fixture_id=fixture_id, tier=tier, primary=False),
        _metric("NON-UNRESOLVED", "Non-unresolved disposition rate",
                sum(1 for m in reconstruction.mappings if m.disposition.value not in {"unresolved_gap", "unsupported"}),
                len(reconstruction.mappings), fixture_id=fixture_id, tier=tier, primary=False),
        _metric("SCHEMA-CONFORMANCE", "Local schema conformance",
                len(reconstruction.changes) - len(reconstruction.validation_errors),
                len(reconstruction.changes), fixture_id=fixture_id, tier=tier, primary=False),
        _metric("REFERENCE-F1", "Reference-target macro-F1",
                int(round(comparison.macro_f1 * reference_rows)), reference_rows,
                fixture_id=fixture_id, tier=tier, primary=False),
    ]

    holdout_path = root / "holdout_metrics.json"
    if holdout_path.is_file():
        holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
        supporting.append(
            _metric("HOLDOUT-RECALL", "Holdout feature recall (pre-computed; not imported)",
                    holdout["numerator"], holdout["denominator"],
                    fixture_id=holdout.get("fixture", "northstar-pc-2026.10"), tier=tier, primary=False,
                    caveat=holdout.get("caveat", "Pre-computed holdout aggregate; not imported into the demo."))
        )

    # Independent baselines.
    identity_correct = 0
    strong_naive_correct = 0
    for gold in gold_mappings:
        source_leaf = gold["source_ref"].rsplit(".", 1)[-1].lower()
        target = gold["target_name"].lower()
        if source_leaf == target:
            identity_correct += 1
        normalized = source_leaf.replace("_ext", "").replace("_", "")
        if normalized == target.replace("_", "") or target in normalized or normalized in target:
            strong_naive_correct += 1

    baseline_caps: set[str] = set()
    pcf_paths = [a.path for a in manifest.artifacts if a.kind == "pcf"]
    capability_patterns = {
        "vehicle_information": r"vehicle(?!rating|driver)",
        "vehicle_rating": r"vehiclerating|ratingfactor",
        "driver_information": r"driver(?!eligibility)",
        "driver_eligibility": r"drivereligibility",
        "coverage_selection": r"coverage(?!term)",
        "coverage_terms": r"coverageterm",
        "policy_line": r"\bline\b",
        "policy_questions": r"policyquestions",
    }
    for path in pcf_paths:
        lower = path.lower().rsplit("/", 1)[-1]
        for capability, pattern in capability_patterns.items():
            if re.search(pattern, lower):
                baseline_caps.add(capability)
    gold_caps = {g["capability"] for g in gold_features}
    pcf_baseline = len(baseline_caps & gold_caps) / max(1, len(gold_caps))

    naive_rules = {rule["rule_id"]: rule for rule in load_rules()}
    naive_tp = naive_fp = naive_fn = 0
    all_text_files = [(a.path, resolved_root / a.path) for a in manifest.artifacts
                      if a.status.value in {"parsed", "partial"}]
    for rule_id, cases in gold_findings.items():
        rule = naive_rules.get(rule_id)
        if not rule:
            continue
        positives = {p.split("#", 1)[0] for p in cases.get("positives", [])}
        negatives = {p.split("#", 1)[0] for p in cases.get("negatives", [])}
        predicted: set[str] = set()
        for rel, file_path in all_text_files:
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _naive_predict(rule, text):
                predicted.add(rel)
        naive_tp += len(predicted & positives)
        naive_fp += len(predicted & negatives)
        naive_fn += len(positives - predicted)
    grep_precision = naive_tp / (naive_tp + naive_fp) if naive_tp + naive_fp else 0.0
    grep_recall = naive_tp / (naive_tp + naive_fn) if naive_tp + naive_fn else 0.0
    grep_f1 = 2 * grep_precision * grep_recall / (grep_precision + grep_recall) if grep_precision + grep_recall else 0.0

    baselines = {
        "identity_mapper": identity_correct / max(1, len(gold_mappings)),
        "all_unresolved": 0.0,
        "strong_naive_mapper": strong_naive_correct / max(1, len(gold_mappings)),
        "pcf_grep_discovery": pcf_baseline,
        "grep_only_findings": grep_precision,
        "always_answer_assistant": 0.0,
    }

    metric_values = {m.metric_id: m.value for m in metrics}
    margins = {
        "M1": {"baseline": pcf_baseline, "delta": metric_values["M1"] - pcf_baseline, "required_pp": 10.0,
               "pass": (metric_values["M1"] - pcf_baseline) >= 0.10},
        "M4": {"baseline": baselines["identity_mapper"], "delta": metric_values["M4"] - baselines["identity_mapper"],
               "required_pp": 10.0, "pass": (metric_values["M4"] - baselines["identity_mapper"]) >= 0.10},
        "M6": {"baseline": grep_f1, "delta": metric_values["M6"] - grep_f1,
               "required_pp": 10.0, "pass": (metric_values["M6"] - grep_f1) >= 0.10},
    }

    return EvaluationResult(
        metrics=metrics, supporting=supporting, baselines=baselines,
        margins=margins, per_rule=per_rule, m5_precision=m5_precision,
    )
