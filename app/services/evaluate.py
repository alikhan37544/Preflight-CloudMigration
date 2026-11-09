"""Evaluation harness: six headline metrics, baselines, per-rule table.

Ground truth is read only by this evaluation harness, never by the analysis
pipeline. All numbers are for the controlled synthetic fixture.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from app.models import LocatorKind, Manifest, Metric
from app.services.compare import CompareResult
from app.services.discovery import DiscoveryResult
from app.services.parsers._xml import safe_parser
from app.services.reconstruction import ReconstructionResult
from app.services.redaction import redact_excerpt
from app.services.review import ReviewResult, load_rules
from app.services.textindex import TextIndex

CAVEAT = (
    "One synthetic fixture; demonstration, not a benchmark. "
    "No live tenant and no generalisation to real estates."
)
DEMO_NOTE = "Demo slice is in-sample (a subset of the development fixture)."


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


# Bounded caches keep a large estate from being retained in memory. The naive
# baseline is allowed to skip very large files; the locator audit and grounding
# index still see every file they need (grounding is capped separately).
_MAX_CACHE_BYTES = _env_int("PREFLIGHT_EVAL_CACHE_BYTES", 64 * 1024 * 1024)
_MAX_CACHE_FILE_BYTES = _env_int("PREFLIGHT_EVAL_CACHE_FILE_BYTES", 16 * 1024 * 1024)
_MAX_XML_CACHE_FILES = _env_int("PREFLIGHT_EVAL_XML_CACHE_FILES", 64)
_MAX_XML_CACHE_BYTES = _env_int("PREFLIGHT_EVAL_XML_CACHE_BYTES", 32 * 1024 * 1024)
_MAX_XML_FILE_BYTES = _env_int("PREFLIGHT_EVAL_XML_FILE_BYTES", 8 * 1024 * 1024)
_MAX_GROUNDING_CHARS = _env_int("PREFLIGHT_EVAL_GROUNDING_CHARS", 8 * 1024 * 1024)
_NAIVE_MAX_FILE_BYTES = _env_int("PREFLIGHT_EVAL_NAIVE_MAX_FILE_BYTES", 2 * 1024 * 1024)
_GROUNDING_MAX_FILE_BYTES = _env_int(
    "PREFLIGHT_EVAL_GROUNDING_MAX_FILE_BYTES", 2 * 1024 * 1024
)


@dataclass
class EvaluationResult:
    metrics: list[Metric] = field(default_factory=list)
    supporting: list[Metric] = field(default_factory=list)
    baselines: dict[str, float] = field(default_factory=dict)
    margins: dict[str, dict] = field(default_factory=dict)
    per_rule: dict[str, dict[str, int]] = field(default_factory=dict)
    m5_precision: float = 0.0
    warnings: list[str] = field(default_factory=list)


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        return (0.0, 0.0)
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _metric(metric_id: str, label: str, numerator: int, denominator: int, *,
            fixture_id: str, tier: str, primary: bool, caveat: str = CAVEAT,
            interval: bool = True) -> Metric:
    safe_den = max(1, denominator)
    safe_num = max(0, min(numerator, safe_den))
    low, high = wilson_interval(safe_num, safe_den) if interval else (None, None)
    return Metric(
        metric_id=metric_id, label=label, numerator=safe_num, denominator=safe_den,
        caveat=caveat, fixture_id=fixture_id, tier=tier, primary=primary,
        interval_low=low, interval_high=high,
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _excerpt_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_PLACEHOLDER_EXCERPTS = {
    "not-in-file", "not in file", "not found", "missing", "placeholder",
    "todo", "tbd", "fixme", "lorem ipsum", "n/a", "na", "none", "null",
    "undefined", "redacted", "...", "???",
}
_PLACEHOLDER_PATTERN = re.compile(
    r"^(?:"
    r"(?:todo|tbd|fixme|placeholder|lorem ipsum)\b.*"
    r"|not[-_ ]?in[-_ ]?file\b.*"
    r"|[x*._\-]{3,}"
    r"|(?:\.\.\.|…)+"
    r")$",
    re.IGNORECASE,
)


def _meaningful_excerpt(text: str) -> bool:
    """Reject empty, tiny, and placeholder-like excerpts.

    The support audit is a locator check, not a semantic entailment check, so a
    minimum amount of real text is required before the locator is resolved.
    """
    normalized = _norm(text)
    if len(normalized) < 8:
        return False
    if not re.search(r"[A-Za-z0-9]{3,}", normalized):
        return False
    lowered = normalized.lower()
    if lowered in _PLACEHOLDER_EXCERPTS:
        return False
    if _PLACEHOLDER_PATTERN.fullmatch(lowered):
        return False
    return True


def _line_window_supports(lines: list[str] | TextIndex, line: int | None, excerpt: str,
                          pad: int = 2) -> bool:
    """Require the excerpt inside a small window around the declared line."""
    if isinstance(lines, TextIndex):
        lines = lines.lines
    if line is None or not 1 <= line <= len(lines):
        return False
    wanted = _norm(excerpt)
    excerpt_lines = [item for item in (excerpt or "").strip().splitlines() if _norm(item)]
    if not wanted or not excerpt_lines:
        return False
    span = max(1, len(excerpt_lines))
    start = max(0, line - 1 - pad)
    end = min(len(lines), line - 1 + span + pad)
    if wanted not in _norm("\n".join(lines[start:end])):
        return False
    first = _norm(excerpt_lines[0])
    near_start = max(0, line - 1 - pad)
    near_end = min(len(lines), line + pad)
    return bool(first) and first in _norm("\n".join(lines[near_start:near_end]))


class _EvalCache:
    """Bounded text/line/XML cache for one evaluation run."""

    def __init__(self) -> None:
        self._text: dict[str, str] = {}
        self._text_bytes = 0
        self._missing: set[str] = set()
        self._indexes: dict[str, TextIndex] = {}
        self._redacted: dict[str, str] = {}
        self._redacted_indexes: dict[str, TextIndex] = {}
        self._xml: dict[str, etree._ElementTree | None] = {}
        self._xml_order: list[str] = []
        self._xml_sizes: dict[str, int] = {}
        self._xml_bytes = 0

    def read_text(self, path: Path) -> str | None:
        key = str(path)
        cached = self._text.get(key)
        if cached is not None:
            return cached
        if key in self._missing:
            return None
        try:
            if path.stat().st_size > _MAX_CACHE_FILE_BYTES:
                # Still available for one-off checks, but not retained.
                return path.read_text(encoding="utf-8", errors="replace")
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            self._missing.add(key)
            return None
        if self._text_bytes + len(text) <= _MAX_CACHE_BYTES:
            self._text[key] = text
            self._text_bytes += len(text)
        return text

    def read_text_if_small(self, path: Path, limit: int) -> str | None:
        key = str(path)
        if key in self._text:
            return self._text[key]
        if key in self._missing:
            return None
        try:
            if path.stat().st_size > limit:
                return None
        except OSError:
            self._missing.add(key)
            return None
        return self.read_text(path)

    def index(self, path: Path) -> TextIndex | None:
        key = str(path)
        cached = self._indexes.get(key)
        if cached is not None:
            return cached
        text = self.read_text(path)
        if text is None:
            return None
        index = TextIndex(text)
        if key in self._text and key not in self._indexes:
            self._indexes[key] = index
        return index

    def redacted_text(self, path: Path) -> str | None:
        key = str(path)
        if key in self._redacted:
            return self._redacted[key]
        text = self.read_text(path)
        if text is None:
            return None
        clean, _ = redact_excerpt(text)
        if key in self._text:
            self._redacted[key] = clean
        return clean

    def redacted_index(self, path: Path) -> TextIndex | None:
        key = str(path)
        cached = self._redacted_indexes.get(key)
        if cached is not None:
            return cached
        text = self.redacted_text(path)
        if text is None:
            return None
        index = TextIndex(text)
        if key in self._redacted:
            self._redacted_indexes[key] = index
        return index

    def xml_tree(self, path: Path) -> etree._ElementTree | None:
        key = str(path)
        if key in self._xml:
            return self._xml[key]
        try:
            size = path.stat().st_size
            if (size > _MAX_XML_FILE_BYTES
                    or len(self._xml) >= _MAX_XML_CACHE_FILES
                    or self._xml_bytes + size > _MAX_XML_CACHE_BYTES):
                tree = etree.parse(str(path), safe_parser())
                _strip_namespaces(tree)
                return tree
            tree = etree.parse(str(path), safe_parser())
            _strip_namespaces(tree)
        except Exception:
            if len(self._xml) < _MAX_XML_CACHE_FILES * 4:
                self._xml[key] = None
            return None
        self._xml[key] = tree
        self._xml_order.append(key)
        self._xml_sizes[key] = size
        self._xml_bytes += size
        while (len(self._xml_order) > _MAX_XML_CACHE_FILES
               or self._xml_bytes > _MAX_XML_CACHE_BYTES):
            stale = self._xml_order.pop(0)
            self._xml.pop(stale, None)
            self._xml_bytes -= self._xml_sizes.pop(stale, 0)
        return tree


class _GroundingIndex:
    """Normalized grounding corpus with a hard character cap."""

    def __init__(self, max_chars: int = _MAX_GROUNDING_CHARS) -> None:
        self.max_chars = max_chars
        self.parts: list[str] = []
        self.length = 0
        self.truncated = False
        self._text: str | None = None

    def add(self, part: str | None) -> None:
        if not part or self.truncated:
            return
        normalized = _norm(part)
        if not normalized:
            return
        separator = 1 if self.length else 0
        remaining = self.max_chars - self.length - separator
        if remaining <= 0:
            self.truncated = True
            return
        if len(normalized) > remaining:
            normalized = normalized[:remaining]
            self.truncated = True
        self.parts.append(normalized)
        self.length += len(normalized) + separator

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = " ".join(self.parts).lower()
        return self._text


def _strip_namespaces(tree: etree._ElementTree) -> None:
    for element in tree.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            element.tag = etree.QName(element).localname
    etree.cleanup_namespaces(tree)


def _xpath_supports(path: Path, xpath: str, excerpt: str,
                    cache: _EvalCache | None = None) -> bool | None:
    """Resolve the XPath; ``None`` means resolution was impossible."""
    try:
        tree = cache.xml_tree(path) if cache is not None else etree.parse(
            str(path), safe_parser()
        )
        if tree is None:
            return None
        if cache is None:
            _strip_namespaces(tree)
    except Exception:
        return None
    stripped = re.sub(r"(?<![:\w-])([A-Za-z_][\w.-]*):(?=[A-Za-z_*])", "", xpath)
    candidates = [xpath] if stripped == xpath else [xpath, stripped]
    elements = None
    evaluated = False
    for expression in candidates:
        try:
            found = tree.xpath(expression)
        except Exception:
            continue
        evaluated = True
        if found:
            elements = found
            break
    if elements is None:
        # A syntactically valid expression with no hit is a wrong locator; only
        # an expression we could not evaluate at all may use the line fallback.
        return False if evaluated else None
    wanted = _norm(excerpt)
    for element in elements:
        if isinstance(element, etree._Element):
            try:
                serialized = etree.tostring(element, encoding="unicode", with_tail=True)
            except Exception:
                serialized = ""
            values = (serialized, element.text or "", element.tail or "")
        else:
            values = (str(element),)
        if any(wanted in _norm(value) for value in values):
            return True
    return False


def audit_evidence_support(root: Path, evidence,
                           cache: _EvalCache | None = None) -> bool:
    """Check that a link resolves inside the fixture and the excerpt appears.

    Redacted review evidence is checked against a redacted copy of the source so
    that a persisted fingerprint remains verifiable without retaining secrets.
    An optional ``cache`` keeps the text, lines, and parsed XML for a path so
    one evaluation does not reread the same file for every evidence item.
    """
    excerpt = evidence.excerpt or ""
    if not _meaningful_excerpt(excerpt):
        return False
    digest = _excerpt_digest(excerpt)
    if evidence.excerpt_sha != digest:
        return False
    if evidence.locator.excerpt_sha and evidence.locator.excerpt_sha != digest:
        return False
    try:
        root_path = Path(root).resolve()
        path = (root_path / evidence.path).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    if not path.is_relative_to(root_path):
        return False
    if not path.is_file():
        return False
    redacted = bool(getattr(evidence, "redacted", False))
    if cache is not None:
        if redacted:
            text = cache.redacted_text(path)
            lines = cache.redacted_index(path)
        else:
            text = cache.read_text(path)
            lines = cache.index(path)
    else:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        if redacted:
            text, _ = redact_excerpt(text)
        lines = TextIndex(text)
    if text is None or lines is None:
        return False
    if evidence.locator.kind is LocatorKind.XPATH and not redacted:
        # An XPath claim must resolve and support the excerpt. An invalid or
        # unevaluable expression is a failed locator, not a line fallback.
        return bool(_xpath_supports(path, evidence.locator.value, excerpt, cache=cache))
    return _line_window_supports(lines, evidence.locator.line, excerpt)


_GROUNDING_TOKEN = re.compile(r"[A-Za-z0-9]+")
_COMMON_GROUNDING_TOKENS = frozenset({
    "auto", "config", "configuration", "coverage", "data", "driver", "entity",
    "factor", "field", "form", "info", "information", "line", "name", "object",
    "personal", "policy", "question", "questions", "rating", "record", "screen",
    "selection", "table", "template", "term", "terms", "type", "value", "vehicle",
})


def _grounding_tokens(mapping) -> list[str]:
    tokens: list[str] = []
    for raw in (mapping.source_ref or "", mapping.source_name or ""):
        for token in _GROUNDING_TOKEN.findall(raw):
            lowered = token.lower()
            if len(lowered) >= 3 and lowered not in tokens:
                tokens.append(lowered)
    return tokens


def _add_grounding_evidence(index: _GroundingIndex, manifest: Manifest,
                            discovery: DiscoveryResult,
                            supported_evidence: list | None = None) -> None:
    allowed = None if supported_evidence is None else {id(item) for item in supported_evidence}
    for item in discovery.evidence:
        if item.excerpt and (allowed is None or id(item) in allowed):
            index.add(item.excerpt)
    for path in manifest.unsupported_paths:
        index.add(path)


def _mapping_grounding_text(root: Path, manifest: Manifest,
                            discovery: DiscoveryResult,
                            supported_evidence: list | None = None) -> str:
    """Evidence text that can ground a mapping on a non-empty snapshot.

    The public helper retains its string result, but builds it through the
    bounded index (and a bounded per-file read) so callers cannot accidentally
    retain an entire large estate.
    """
    if manifest.file_count <= 0:
        return ""
    index = _GroundingIndex()
    _add_grounding_evidence(index, manifest, discovery, supported_evidence)
    cache = _EvalCache()
    for artifact in manifest.artifacts:
        index.add(artifact.path)
        if artifact.status.value not in {"parsed", "partial"} or index.truncated:
            continue
        path = root / artifact.path
        text = cache.read_text_if_small(path, _GROUNDING_MAX_FILE_BYTES)
        if text is not None:
            index.add(text)
    return index.text


def _mapping_grounded(mapping, grounding_text: str | _GroundingIndex,
                      manifest: Manifest) -> bool:
    """Require real snapshot text, not a generic single-word match.

    A mapping passes when its full ``source_ref`` appears, or when at least two
    of its significant source tokens appear and at least one of those is not a
    generic domain word. Empty values and a lone ``Vehicle``/``Policy`` token
    cannot ground a mapping.
    """
    if isinstance(grounding_text, _GroundingIndex):
        grounding_text = grounding_text.text
    if manifest.file_count <= 0 or not grounding_text:
        return False
    tokens = _grounding_tokens(mapping)
    non_common = {token for token in tokens if token not in _COMMON_GROUNDING_TOKENS}
    if not non_common:
        return False
    source_ref = _norm(mapping.source_ref or "").lower()
    if (source_ref and source_ref in grounding_text
            and (len(tokens) >= 2 or source_ref not in _COMMON_GROUNDING_TOKENS)):
        return True
    matched = {token for token in tokens if token in grounding_text}
    return len(matched) >= 2 and bool(matched & non_common)


def _explicit_issue_anchors(issue: dict) -> set[str]:
    for key in ("anchors", "anchor", "evidence_paths", "evidence", "paths", "path"):
        value = issue.get(key)
        if isinstance(value, str) and value:
            return {value}
        if isinstance(value, list):
            anchors = {str(item) for item in value if item}
            if anchors:
                return anchors
    return set()


def _issue_anchors(issue: dict, gold_findings: dict, gold_mappings: list[dict]) -> set[str]:
    explicit = _explicit_issue_anchors(issue)
    if explicit:
        return explicit
    kind = issue.get("signal_type")
    signal = issue.get("signal")
    if kind == "finding_rule":
        cases = gold_findings.get(signal, {})
        return {path.split("#", 1)[0] for path in cases.get("positives", [])}
    if kind == "mapping_rule":
        return {mapping["source_ref"] for mapping in gold_mappings if mapping.get("rule_id") == signal}
    return set()


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


_NAIVE_SECRET = re.compile(
    r'(?i)(api[_-]?key|secret|password|token|credential)\s*=\s*"'
)
_NAIVE_EMPTY_CATCH = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")
_NAIVE_LONG_TYPE = re.compile(r'name="([^"]{25,})"')
_NAIVE_LOG_PII = re.compile(r"(?i)(VIN|SSN|password|license)")
_NAIVE_DB_TOKENS = ("Query.make", "loadSampleData", "DriverManager.getConnection")


def _compile_naive(rule: dict) -> tuple[str, object]:
    """Precompile one baseline matcher so a file pass does not recompile regexes."""
    detection = rule.get("detection", {})
    kind = detection.get("kind")
    if kind == "gosu_regex":
        return kind, tuple(re.compile(pattern) for pattern in detection.get("patterns", []))
    if kind == "secret_assignment":
        return kind, _NAIVE_SECRET
    if kind == "empty_catch":
        return kind, _NAIVE_EMPTY_CATCH
    if kind == "long_type_name":
        return kind, _NAIVE_LONG_TYPE
    if kind == "log_pii":
        return kind, _NAIVE_LOG_PII
    return str(kind), None


def _naive_predict_compiled(spec: tuple[str, object], text: str) -> bool:
    kind, compiled = spec
    if kind == "gosu_regex":
        return any(pattern.search(text) for pattern in compiled)  # type: ignore[union-attr]
    if kind == "secret_assignment":
        return bool(compiled.search(text))  # type: ignore[union-attr]
    if kind == "commit_in_block":
        return "runWithNewBundle" in text and "commit(" in text
    if kind == "empty_catch":
        return bool(compiled.search(text))  # type: ignore[union-attr]
    if kind == "gunit_db":
        return any(token in text for token in _NAIVE_DB_TOKENS)
    if kind == "long_type_name":
        return bool(compiled.search(text))  # type: ignore[union-attr]
    if kind == "log_pii":
        return bool(compiled.search(text))  # type: ignore[union-attr]
    return False


def _naive_predict(rule: dict, text: str) -> bool:
    """Compatibility wrapper; evaluation uses the precompiled spec."""
    return _naive_predict_compiled(_compile_naive(rule), text)


_INLINE_GLOBAL_FLAGS = re.compile(r"^\(\?[aiLmsux]+\)")
_REGEX_META = set("[](){}*+?|^$")


def _regex_literal_hint(pattern: re.Pattern) -> str | None:
    """Longest literal run that every match of ``pattern`` must contain."""
    source = _INLINE_GLOBAL_FLAGS.sub("", pattern.pattern)
    runs: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 1
            if index >= len(source):
                break
            escaped = source[index]
            if escaped in "bBAZ":
                if current:
                    runs.append("".join(current))
                    current = []
            elif escaped in "dDsSwW":
                if current:
                    runs.append("".join(current))
                    current = []
            else:
                current.append(escaped)
        elif char in _REGEX_META:
            if current:
                runs.append("".join(current))
                current = []
            if char == "[":
                # Skip a character class; it is not a required literal.
                close = source.find("]", index)
                index = len(source) if close == -1 else close
        elif char == "(" and source.startswith("(?", index):
            # Inline flags/lookarounds are zero-width; keep any literal after.
            close = source.find(":", index)
            if close != -1:
                group = source[index:close]
                if group in {"(?:", "(?=", "(?!", "(?<=", "(?<!"}:
                    pass
                index = close if close != -1 else index
            elif current:
                runs.append("".join(current))
                current = []
        else:
            current.append(char)
        index += 1
    if current:
        runs.append("".join(current))
    candidates = [run for run in runs if len(run) >= 3]
    if not candidates:
        return None
    # The first run is the common prefix before any alternation/optional group;
    # a later run may belong to only one branch and would be an unsafe filter.
    return candidates[0].lower()


def _compile_naive_prefilter(specs) -> tuple[str, ...] | None:
    """Lowercase literals whose absence proves every baseline rule is false.

    A tuple of literal ``in`` checks is much cheaper than running eight regexes
    over every large filler file. A hit falls through to the exact per-rule
    matchers, so results are unchanged.
    """
    hints: list[str] = []
    for kind, compiled in specs:
        if kind == "gosu_regex":
            for pattern in compiled:
                hint = _regex_literal_hint(pattern)
                if hint is None:
                    return None
                hints.append(hint)
        elif kind == "secret_assignment":
            hints.extend(("api", "secret", "password", "token", "credential"))
        elif kind == "log_pii":
            hints.extend(("vin", "ssn", "password", "license"))
        elif kind in {"empty_catch", "long_type_name"}:
            hint = _regex_literal_hint(compiled)
            if hint is None:
                return None
            hints.append(hint)
        elif kind == "commit_in_block":
            hints.extend(("runwithnewbundle", "commit("))
        elif kind == "gunit_db":
            hints.extend(token.lower() for token in _NAIVE_DB_TOKENS)
    if not hints:
        return None
    return tuple(dict.fromkeys(hints))


def evaluate_run(*, fixture_id: str, manifest: Manifest, discovery: DiscoveryResult,
                 reconstruction: ReconstructionResult, review: ReviewResult,
                 comparison: CompareResult, ground_truth_dir: Path, tier: str,
                 fixture_root: Path | None = None) -> EvaluationResult:
    root = Path(ground_truth_dir)
    resolved_root = Path(fixture_root) if fixture_root is not None else Path("fixtures") / fixture_id
    warnings: list[str] = []
    gold_features = json.loads((root / "features.json").read_text(encoding="utf-8"))["features"]
    gold_mappings = json.loads((root / "mappings.json").read_text(encoding="utf-8"))["mappings"]
    gold_findings = json.loads((root / "findings.json").read_text(encoding="utf-8"))["rules"]

    # Audit every discovery link once. Only locator-supported evidence may anchor
    # a feature, ground a mapping, or support the headline evidence metric.
    cache = _EvalCache()
    supported_discovery = [
        item for item in discovery.evidence
        if audit_evidence_support(resolved_root, item, cache=cache)
    ]
    supported_by_id: dict[str, list] = defaultdict(list)
    for item in supported_discovery:
        supported_by_id[item.evidence_id].append(item)
    feature_paths = {
        f.feature_id: {
            item.path
            for eid in f.evidence_ids
            for item in supported_by_id.get(eid, [])
        }
        for f in discovery.features
    }

    # M1/M2: require the capability and at least one audited gold anchor path.
    # Each gold feature can consume at most one emitted feature, so duplicates
    # become FP.
    matched_gold = 0
    used_features: set[int] = set()
    for gold in gold_features:
        anchors = set(gold.get("anchors", []))
        for index, feature in enumerate(discovery.features):
            if index in used_features:
                continue
            if (feature.capability == gold["capability"]
                    and feature_paths.get(feature.feature_id, set()) & anchors):
                matched_gold += 1
                used_features.add(index)
                break
    emitted_correct = len(used_features)

    # M3: audit all discovery links. The 30-link stratified sample is retained as
    # a supporting cross-check so a single aggregate cannot hide a bad tail item.
    evidence_good = len(supported_discovery)
    sample = _stratified_sample(discovery.evidence, 30)
    supported_objects = {id(item) for item in supported_discovery}
    sample_good = sum(1 for item in sample if id(item) in supported_objects)

    # Grounding and the grep baseline share one pass over parsed/partial files.
    # The grounding corpus is capped; the naive baseline skips files above the
    # configured cap (and reports that caveat once).
    grounding = _GroundingIndex()
    if manifest.file_count > 0:
        _add_grounding_evidence(grounding, manifest, discovery, supported_discovery)
    naive_rules = {rule["rule_id"]: rule for rule in load_rules()}
    naive_specs = {
        rule_id: _compile_naive(naive_rules[rule_id])
        for rule_id in gold_findings if rule_id in naive_rules
    }
    # The baseline metrics only intersect predictions with labelled paths:
    # unlabelled files cannot change TP/FP/FN. Scanning only labelled files is
    # therefore output-identical and avoids rereading an unrelated estate.
    naive_targets: set[str] = set()
    for cases in gold_findings.values():
        naive_targets.update(
            path.split("#", 1)[0] for path in cases.get("positives", [])
        )
        naive_targets.update(
            path.split("#", 1)[0] for path in cases.get("negatives", [])
        )
    predicted_by_rule: dict[str, set[str]] = {
        rule_id: set() for rule_id in naive_specs
    }
    naive_prefilter = _compile_naive_prefilter(naive_specs.values())
    skipped_large = 0
    for artifact in manifest.artifacts:
        if manifest.file_count > 0 and not grounding.truncated:
            grounding.add(artifact.path)
        if artifact.status.value not in {"parsed", "partial"}:
            continue
        is_naive_target = artifact.path in naive_targets and bool(predicted_by_rule)
        needs_grounding = manifest.file_count > 0 and not grounding.truncated
        if not is_naive_target and not needs_grounding:
            # Once grounding is capped there is no work left for this file.
            continue
        path = resolved_root / artifact.path
        try:
            size = path.stat().st_size
        except OSError:
            continue
        text = None
        naive_text = None
        if is_naive_target:
            if size <= _NAIVE_MAX_FILE_BYTES:
                naive_text = text = cache.read_text(path)
            else:
                skipped_large += 1
        if (manifest.file_count > 0 and not grounding.truncated
                and size <= _GROUNDING_MAX_FILE_BYTES):
            if text is None:
                text = cache.read_text(path)
            if text is not None:
                grounding.add(text)
        if naive_text is not None:
            if naive_prefilter is not None:
                lowered = naive_text.lower()
                if not any(hint in lowered for hint in naive_prefilter):
                    continue
            for rule_id, spec in naive_specs.items():
                if _naive_predict_compiled(spec, naive_text):
                    predicted_by_rule[rule_id].add(artifact.path)
    if skipped_large:
        warnings.append(
            f"Naive grep baseline skipped {skipped_large} file(s) larger than "
            f"{_NAIVE_MAX_FILE_BYTES} bytes."
        )

    # M4: source, target, and disposition must all match; the mapping must also
    # be grounded by snapshot evidence, not merely restate the static rule pack.
    grounded_flags = [
        _mapping_grounded(mapping, grounding, manifest)
        for mapping in reconstruction.mappings
    ]
    used_tool: set[int] = set()
    mapping_correct = 0
    for gold in gold_mappings:
        for index, tool in enumerate(reconstruction.mappings):
            if index in used_tool:
                continue
            if (tool.rule_id == gold["rule_id"]
                    and tool.source_ref == gold["source_ref"]
                    and tool.source_layer == gold["source_layer"]
                    and tool.target_path == gold["target_path"]
                    and tool.target_name == gold["target_name"]
                    and tool.disposition.value == gold["disposition"]
                    and grounded_flags[index]):
                mapping_correct += 1
                used_tool.add(index)
                break
    extra_mappings = len(reconstruction.mappings) - len(used_tool)
    mapping_denominator = len(gold_mappings) + extra_mappings

    # M5: planted estimate-moving issues, ranked top-8 precision guard. A rule ID
    # alone is insufficient: the expected finding path or mapping anchor must be
    # present in the output.
    issues_path = root / "estimate_moving_issues.json"
    issues_payload = json.loads(issues_path.read_text(encoding="utf-8")) if issues_path.is_file() else {"issues": [], "decoys": []}
    manifest_paths = {artifact.path for artifact in manifest.artifacts}
    review_evidence_by_id = {item.evidence_id: item for item in review.evidence}
    review_supported = {
        item.evidence_id: audit_evidence_support(resolved_root, item, cache=cache)
        for item in review.evidence
    }
    finding_paths: dict[str, set[str]] = defaultdict(set)
    for finding in review.findings:
        links = [review_evidence_by_id.get(evidence_id) for evidence_id in finding.evidence_ids]
        if not links or any(ev is None or not review_supported.get(ev.evidence_id) for ev in links):
            continue
        for ev in links:
            finding_paths[finding.rule_id].add(ev.path)
    mapping_outputs: dict[str, set[str]] = defaultdict(set)
    for mapping, grounded in zip(reconstruction.mappings, grounded_flags):
        if not grounded:
            continue
        mapping_outputs[mapping.rule_id].update(
            {mapping.source_ref, mapping.target_path, mapping.target_name}
        )
    detected_issues: set[str] = set()
    issues = issues_payload.get("issues", [])
    for issue in issues:
        kind = issue.get("signal_type")
        signal = issue.get("signal")
        anchors = _issue_anchors(issue, gold_findings, gold_mappings)
        if not anchors:
            continue
        if kind == "finding_rule":
            found_paths = finding_paths.get(signal, set()) & manifest_paths
            if found_paths & anchors:
                detected_issues.add(issue["id"])
        elif kind == "mapping_rule":
            if mapping_outputs.get(signal, set()) & anchors:
                detected_issues.add(issue["id"])
    issue_ids = {issue["id"] for issue in issues}
    m5_recall_num = len(detected_issues & issue_ids)
    decoys = issues_payload.get("decoys", [])
    top8_slots = min(8, len(issue_ids) + len(decoys))
    m5_top8_num = min(m5_recall_num, top8_slots)
    m5_precision = (m5_top8_num / top8_slots) if top8_slots else 0.0

    # M6: micro-F1 over labelled positives/negatives; per-rule macro reported separately.
    # Only findings with at least one locator-supported evidence link contribute a
    # path. Any supported path that is not a labelled positive is a false positive,
    # including findings on files that the gold set does not label at all.
    per_rule: dict[str, dict[str, int]] = {}
    tp_total = fp_total = fn_total = 0
    f1_scores: list[float] = []
    for rule_id, cases in gold_findings.items():
        positives = {p.split("#", 1)[0] for p in cases.get("positives", [])}
        found = finding_paths.get(rule_id, set())
        tp = len(found & positives)
        fp = len(found - positives)
        fn = len(positives - found)
        per_rule[rule_id] = {"tp": tp, "fp": fp, "fn": fn}
        tp_total += tp
        fp_total += fp
        fn_total += fn
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1_scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    extra_rule_fp = sum(
        len(paths) for rule_id, paths in finding_paths.items() if rule_id not in gold_findings
    )
    if extra_rule_fp:
        per_rule["UNLABELLED"] = {"tp": 0, "fp": extra_rule_fp, "fn": 0}
        fp_total += extra_rule_fp
    macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    f1_den = 2 * tp_total + fp_total + fn_total

    metrics = [
        _metric("M1", "Feature discovery recall", matched_gold, len(gold_features),
                fixture_id=fixture_id, tier=tier, primary=True,
                caveat=CAVEAT + " Anchors count only when the linked evidence passes the locator-support audit. " + DEMO_NOTE),
        _metric("M2", "Feature discovery precision", emitted_correct, len(discovery.features),
                fixture_id=fixture_id, tier=tier, primary=True,
                caveat=CAVEAT + " Anchors count only when the linked evidence passes the locator-support audit. " + DEMO_NOTE),
        _metric("M3", "Evidence-link support precision (all links)", evidence_good,
                len(discovery.evidence),
                fixture_id=fixture_id, tier=tier, primary=True,
                caveat=CAVEAT + " Every discovery link is audited for path containment, excerpt SHA, non-placeholder excerpt, and locator support; support is not semantic entailment. " + DEMO_NOTE),
        _metric("M4", "Disposition correctness", mapping_correct, mapping_denominator,
                fixture_id=fixture_id, tier=tier, primary=True,
                caveat=CAVEAT + " A mapping must also be grounded by the full source_ref or at least two significant snapshot tokens. " + DEMO_NOTE),
        _metric("M5", "Estimate-moving issue recall", m5_recall_num, len(issue_ids),
                fixture_id=fixture_id, tier=tier, primary=True,
                caveat=CAVEAT + f" Top-8 allowance: {m5_top8_num} TP / {top8_slots} slots. " + DEMO_NOTE),
        _metric("M6", "Finding micro-F1 (2TP / (2TP+FP+FN))", 2 * tp_total, f1_den,
                fixture_id=fixture_id, tier=tier, primary=True,
                caveat=CAVEAT + f" {tp_total} TP / {fp_total} FP / {fn_total} FN across 8 rules; TP requires at least one locator-supported evidence link on a labelled positive path. Fraction is the F1 numerator/denominator. No F1 interval; bootstrap deferred. " + DEMO_NOTE,
                interval=False),
    ]

    reference_rows = len(comparison.rows) or 1
    silent_den = len(gold_mappings)
    supporting = [
        _metric("M3-SAMPLE", "30-link stratified sample", sample_good, len(sample),
                fixture_id=fixture_id, tier=tier, primary=False,
                caveat=(
                    "Deterministic round-robin across sorted evidence paths; supporting "
                    "cross-check only, not the headline. Support is not semantic entailment."
                )),
        _metric("M5-TOP8", "M5 top-8 allowance (TP / slots)", m5_top8_num, top8_slots,
                fixture_id=fixture_id, tier=tier, primary=False,
                caveat=(
                    f"{len(issue_ids)} planted issues plus {len(decoys)} fixed decoy allowances; "
                    "stable top-8 denominator, not a full ranking of all tool output."
                )),
        _metric("M6-MACRO", "Finding macro-F1 (sum of per-rule F1 / rules)", int(round(macro_f1 * len(f1_scores))), len(f1_scores),
                fixture_id=fixture_id, tier=tier, primary=False,
                caveat="Macro average across rules; scaled proportion, not a count; demo corpus n=3 positives + 3 negatives per rule.", interval=False),
        _metric("SILENT-OMISSION", "Silent omission rate", len(reconstruction.silent_omissions),
                silent_den, fixture_id=fixture_id, tier=tier, primary=False),
        _metric("NON-UNRESOLVED", "Non-unresolved disposition rate",
                sum(1 for m in reconstruction.mappings if m.disposition.value not in {"unresolved_gap", "unsupported"}),
                len(reconstruction.mappings), fixture_id=fixture_id, tier=tier, primary=False),
        _metric("SCHEMA-CONFORMANCE", "Local schema conformance",
                len(reconstruction.changes) - len(reconstruction.validation_errors),
                len(reconstruction.changes), fixture_id=fixture_id, tier=tier, primary=False),
        _metric("REFERENCE-F1", "Reference-target macro-F1 (scaled to rows)",
                int(round(comparison.macro_f1 * reference_rows)), reference_rows,
                fixture_id=fixture_id, tier=tier, primary=False, interval=False,
                caveat=CAVEAT + " Scaled proportion, not a count."),
    ]

    holdout_path = root / "holdout_metrics.json"
    holdout_base = "Pre-computed holdout aggregate; not imported into the demo."
    holdout_fixture = "northstar-pc-2026.10"
    holdout_num, holdout_den = 0, 1
    if not holdout_path.is_file():
        holdout_caveat = (
            "INVALID holdout aggregate; clamped for display (aggregate absent). "
            + holdout_base
        )
        warnings.append("Holdout aggregate absent; reported as an explicit invalid metric.")
    else:
        try:
            holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            holdout = None
            warnings.append("Holdout aggregate unreadable; reported as an explicit invalid metric.")
        if not isinstance(holdout, dict):
            holdout_caveat = (
                "INVALID holdout aggregate; clamped for display (aggregate unreadable). "
                + holdout_base
            )
        else:
            holdout_fixture = str(holdout.get("fixture") or holdout_fixture)
            raw_num = holdout.get("numerator")
            raw_den = holdout.get("denominator")
            numeric = (
                isinstance(raw_num, int) and not isinstance(raw_num, bool)
                and isinstance(raw_den, int) and not isinstance(raw_den, bool)
            )
            if numeric and raw_den > 0 and 0 <= raw_num <= raw_den:
                holdout_num, holdout_den = raw_num, raw_den
                holdout_caveat = str(holdout.get("caveat") or holdout_base)
            else:
                holdout_den = max(1, raw_den) if numeric else 1
                holdout_num = max(0, min(raw_num, holdout_den)) if numeric else 0
                holdout_caveat = (
                    "INVALID holdout aggregate; clamped for display. "
                    + str(holdout.get("caveat") or holdout_base)
                )
                warnings.append("Invalid holdout aggregate; clamped for display.")
    supporting.append(
        _metric("HOLDOUT-RECALL", "Holdout capability recall (pre-computed; naming-shift only; not imported)",
                holdout_num, holdout_den,
                fixture_id=holdout_fixture, tier=tier, primary=False,
                caveat=holdout_caveat)
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

    naive_tp = naive_fp = naive_fn = 0
    for rule_id, cases in gold_findings.items():
        if rule_id not in naive_specs:
            continue
        positives = {p.split("#", 1)[0] for p in cases.get("positives", [])}
        negatives = {p.split("#", 1)[0] for p in cases.get("negatives", [])}
        predicted = predicted_by_rule[rule_id]
        naive_tp += len(predicted & positives)
        naive_fp += len(predicted & negatives)
        naive_fn += len(positives - predicted)
    grep_precision = naive_tp / (naive_tp + naive_fp) if naive_tp + naive_fp else 0.0
    grep_recall = naive_tp / (naive_tp + naive_fn) if naive_tp + naive_fn else 0.0
    grep_f1 = 2 * grep_precision * grep_recall / (grep_precision + grep_recall) if grep_precision + grep_recall else 0.0

    baselines = {
        "identity_mapper": identity_correct / max(1, len(gold_mappings)),
        "all_unresolved": 0.0,
        "normalized_name_mapper": strong_naive_correct / max(1, len(gold_mappings)),
        "pcf_grep_discovery": pcf_baseline,
        "grep_only_findings": grep_precision,
        "grep_only_findings_f1": grep_f1,
        "always_answer_assistant_refusal_recall": 0.0,
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
        warnings=warnings,
    )
