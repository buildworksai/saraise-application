"""Typed, versioned process-mining extension contracts and local algorithms.

The registry is the public extension seam: paid modules can add namespaced
adapters without importing this module's ORM.  Registration never replaces an
existing implementation implicitly.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
import threading
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable
from xml.etree.ElementTree import Element, SubElement, tostring


class AdapterError(RuntimeError):
    """Base class for trustworthy, typed adapter failures."""


class CapabilityUnavailable(AdapterError):
    """The requested adapter is not installed or healthy."""


class DuplicateAdapterError(AdapterError):
    """An adapter id was already claimed by another implementation."""


class InvalidAdapterResult(AdapterError):
    """An adapter returned evidence outside the canonical contract."""


@dataclass(frozen=True, slots=True)
class AdapterMetadata:
    adapter_id: str
    spi_version: str
    implementation_version: str
    capabilities: tuple[str, ...]
    parameter_schema: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if "." not in self.adapter_id or not all(part for part in self.adapter_id.split(".")):
            raise ValueError("adapter_id must be stable and namespaced")
        if not self.spi_version or not self.implementation_version or not self.capabilities:
            raise ValueError("adapter metadata requires versions and capabilities")


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    case_id: str
    activity: str
    occurred_at: datetime
    resource: str = ""
    source_module: str = "canonical"
    source_event_id: str = ""
    attributes: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConformanceDeviationResult:
    case_id: str
    deviation_type: str
    expected: str
    actual: str
    position: int
    description: str


@dataclass(frozen=True, slots=True)
class CaseFitnessResult:
    case_id: str
    fitness: Decimal
    is_conformant: bool
    deviation_count: int
    trace_length: int


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    fitness: Decimal
    precision: Decimal
    generalization: Decimal
    cases: tuple[CaseFitnessResult, ...]
    deviations: tuple[ConformanceDeviationResult, ...]


@dataclass(frozen=True, slots=True)
class BottleneckResult:
    findings: tuple[Mapping[str, object], ...]
    variants: tuple[Mapping[str, object], ...]
    total_cases: int
    average_case_duration_seconds: Decimal


@runtime_checkable
class EventSourceAdapter(Protocol):
    metadata: AdapterMetadata

    def validate_source(self, source_module: str) -> bool: ...

    def map_event(self, event: Mapping[str, object]) -> Mapping[str, object]: ...


@runtime_checkable
class MiningAlgorithm(Protocol):
    metadata: AdapterMetadata

    def discover(self, events: Sequence[CanonicalEvent], parameters: Mapping[str, object]) -> Mapping[str, object]: ...


@runtime_checkable
class ConformanceAlgorithm(Protocol):
    metadata: AdapterMetadata

    def evaluate(
        self, model: Mapping[str, object], traces: Mapping[str, Sequence[CanonicalEvent]]
    ) -> ConformanceResult: ...


@runtime_checkable
class BottleneckAlgorithm(Protocol):
    metadata: AdapterMetadata

    def analyze(
        self, traces: Mapping[str, Sequence[CanonicalEvent]], time_range: tuple[datetime, datetime]
    ) -> BottleneckResult: ...


@runtime_checkable
class ExportFormatter(Protocol):
    metadata: AdapterMetadata
    content_type: str
    extension: str

    def write(self, events: Iterable[CanonicalEvent], destination: TextIO) -> int: ...


@runtime_checkable
class InsightProvider(Protocol):
    metadata: AdapterMetadata

    def explain(self, evidence: Mapping[str, object]) -> Mapping[str, object]: ...


class AdapterRegistry:
    def __init__(self) -> None:
        self._items: dict[str, object] = {}
        self._lock = threading.RLock()

    def register(self, adapter: object) -> object:
        metadata = getattr(adapter, "metadata", None)
        if not isinstance(metadata, AdapterMetadata):
            raise TypeError("adapter must expose validated AdapterMetadata")
        with self._lock:
            if metadata.adapter_id in self._items:
                raise DuplicateAdapterError(f"Adapter {metadata.adapter_id!r} is already registered")
            self._items[metadata.adapter_id] = adapter
        return adapter

    def get(self, adapter_id: str) -> object:
        candidates = (adapter_id, f"process_mining.{adapter_id}")
        with self._lock:
            for candidate in candidates:
                if candidate in self._items:
                    return self._items[candidate]
        raise CapabilityUnavailable(f"Adapter {adapter_id!r} is unavailable")

    def remove(self, adapter_id: str) -> object | None:
        with self._lock:
            return self._items.pop(adapter_id, None)

    def catalog(self) -> tuple[AdapterMetadata, ...]:
        with self._lock:
            return tuple(sorted((getattr(value, "metadata") for value in self._items.values()), key=lambda item: item.adapter_id))


registry = AdapterRegistry()


class CanonicalEventSource:
    metadata = AdapterMetadata("process_mining.canonical", "1.0", "1.0.0", ("event_source", "native_ingestion"))

    def validate_source(self, source_module: str) -> bool:
        return bool(source_module and len(source_module) <= 100)

    def map_event(self, event: Mapping[str, object]) -> Mapping[str, object]:
        return dict(event)


def _ordered_traces(events: Sequence[CanonicalEvent]) -> dict[str, list[CanonicalEvent]]:
    traces: dict[str, list[CanonicalEvent]] = defaultdict(list)
    for event in events:
        traces[event.case_id].append(event)
    for trace in traces.values():
        trace.sort(key=lambda event: (event.occurred_at, event.source_event_id, event.activity))
    return dict(sorted(traces.items()))


def _node_id(activity: str) -> str:
    return "activity:" + hashlib.sha256(activity.encode("utf-8")).hexdigest()[:16]


class DirectlyFollowsMiner:
    """Deterministic discovery over observed directly-follows evidence."""

    metadata = AdapterMetadata("process_mining.alpha_miner", "1.0", "1.0.0", ("discovery", "frequency"))
    mode = "alpha"

    def _edge_allowed(self, frequency: int, maximum: int, parameters: Mapping[str, object]) -> bool:
        del frequency, maximum, parameters
        return True

    def discover(self, events: Sequence[CanonicalEvent], parameters: Mapping[str, object]) -> Mapping[str, object]:
        if not events:
            raise InvalidAdapterResult("Discovery requires events")
        traces = _ordered_traces(events)
        activity_counts = Counter(event.activity for event in events)
        edge_counts: Counter[tuple[str, str]] = Counter()
        edge_durations: dict[tuple[str, str], list[float]] = defaultdict(list)
        for trace in traces.values():
            sequence = ["__start__", *(event.activity for event in trace), "__end__"]
            for source, target in zip(sequence, sequence[1:]):
                edge_counts[(source, target)] += 1
            for source_event, target_event in zip(trace, trace[1:]):
                edge_durations[(source_event.activity, target_event.activity)].append(
                    max(0.0, (target_event.occurred_at - source_event.occurred_at).total_seconds())
                )
        maximum = max(edge_counts.values(), default=1)
        nodes = [
            {"id": "start", "label": "Start", "type": "start", "frequency": len(traces)},
            *[
                {"id": _node_id(activity), "label": activity, "type": "activity", "frequency": count}
                for activity, count in sorted(activity_counts.items())
            ],
            {"id": "end", "label": "End", "type": "end", "frequency": len(traces)},
        ]
        edges: list[dict[str, object]] = []
        for (source, target), count in sorted(edge_counts.items()):
            if not self._edge_allowed(count, maximum, parameters):
                continue
            durations = edge_durations.get((source, target), [])
            edges.append(
                {
                    "id": hashlib.sha256(f"{source}\0{target}".encode()).hexdigest()[:20],
                    "source": "start" if source == "__start__" else _node_id(source),
                    "target": "end" if target == "__end__" else _node_id(target),
                    "frequency": count,
                    "duration_seconds": round(statistics.mean(durations), 2) if durations else 0,
                }
            )
        graph = {
            "schema_version": "1.0",
            "algorithm": self.metadata.adapter_id,
            "nodes": nodes,
            "edges": edges,
            "extensions": {},
        }
        if not edges:
            raise InvalidAdapterResult("Discovery parameters removed every observed transition")
        return graph


class HeuristicMiner(DirectlyFollowsMiner):
    metadata = AdapterMetadata(
        "process_mining.heuristic_miner",
        "1.0",
        "1.0.0",
        ("discovery", "frequency", "noise_filter"),
        {"dependency_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.8}},
    )
    mode = "heuristic"

    def _edge_allowed(self, frequency: int, maximum: int, parameters: Mapping[str, object]) -> bool:
        threshold = float(parameters.get("dependency_threshold", 0.8))
        if not 0 <= threshold <= 1:
            raise ValueError("dependency_threshold must be between 0 and 1")
        return frequency / maximum >= threshold


class InductiveMiner(DirectlyFollowsMiner):
    metadata = AdapterMetadata(
        "process_mining.inductive_miner",
        "1.0",
        "1.0.0",
        ("discovery", "sound_model", "noise_filter"),
        {"noise_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.2}},
    )
    mode = "inductive"

    def _edge_allowed(self, frequency: int, maximum: int, parameters: Mapping[str, object]) -> bool:
        threshold = float(parameters.get("noise_threshold", 0.2))
        if not 0 <= threshold <= 1:
            raise ValueError("noise_threshold must be between 0 and 1")
        return frequency / maximum >= threshold


class TokenReplayConformance:
    metadata = AdapterMetadata("process_mining.token_replay", "1.0", "1.0.0", ("conformance", "case_evidence"))

    def evaluate(
        self, model: Mapping[str, object], traces: Mapping[str, Sequence[CanonicalEvent]]
    ) -> ConformanceResult:
        edges = model.get("edges")
        nodes = model.get("nodes")
        if not isinstance(edges, list) or not isinstance(nodes, list):
            raise InvalidAdapterResult("Conformance requires a canonical graph")
        labels = {str(node["id"]): str(node.get("label", node["id"])) for node in nodes if isinstance(node, dict) and "id" in node}
        allowed = {(labels.get(str(edge.get("source")), "Start"), labels.get(str(edge.get("target")), "End")) for edge in edges if isinstance(edge, dict)}
        case_results: list[CaseFitnessResult] = []
        deviations: list[ConformanceDeviationResult] = []
        observed_transitions: set[tuple[str, str]] = set()
        for case_id, trace in sorted(traces.items()):
            activities = [event.activity for event in trace]
            sequence = ["Start", *activities, "End"]
            case_deviations = 0
            for position, pair in enumerate(zip(sequence, sequence[1:])):
                observed_transitions.add(pair)
                if pair not in allowed:
                    case_deviations += 1
                    deviations.append(
                        ConformanceDeviationResult(
                            case_id,
                            "unexpected_activity",
                            "",
                            pair[1],
                            max(0, position - 1),
                            f"Transition {pair[0]} → {pair[1]} is absent from the reference model.",
                        )
                    )
            denominator = max(1, len(sequence) - 1)
            fitness = Decimal(max(0, denominator - case_deviations)) / Decimal(denominator)
            case_results.append(CaseFitnessResult(case_id, fitness.quantize(Decimal("0.0001")), case_deviations == 0, case_deviations, len(trace)))
        if not case_results:
            raise InvalidAdapterResult("Conformance requires at least one trace")
        fitness = sum((item.fitness for item in case_results), Decimal(0)) / Decimal(len(case_results))
        precision = Decimal(len(observed_transitions & allowed)) / Decimal(max(1, len(observed_transitions)))
        generalization = Decimal(len(observed_transitions & allowed)) / Decimal(max(1, len(allowed)))
        return ConformanceResult(
            fitness.quantize(Decimal("0.0001")),
            min(Decimal(1), precision).quantize(Decimal("0.0001")),
            min(Decimal(1), generalization).quantize(Decimal("0.0001")),
            tuple(case_results),
            tuple(deviations),
        )


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _severity(median: float, p95: float) -> str:
    ratio = p95 / median if median > 0 else (float("inf") if p95 > 0 else 1)
    if ratio > 10:
        return "critical"
    if ratio > 5:
        return "high"
    if ratio > 2:
        return "medium"
    return "low"


class TransitionDurationAnalyzer:
    metadata = AdapterMetadata("process_mining.transition_duration", "1.0", "1.0.0", ("bottleneck", "variants", "resource_concentration"))

    def analyze(
        self, traces: Mapping[str, Sequence[CanonicalEvent]], time_range: tuple[datetime, datetime]
    ) -> BottleneckResult:
        start, end = time_range
        if end <= start:
            raise ValueError("time range end must follow start")
        transition_durations: dict[tuple[str, str], list[float]] = defaultdict(list)
        transition_resources: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        transition_cases: dict[tuple[str, str], set[str]] = defaultdict(set)
        variants: Counter[tuple[str, ...]] = Counter()
        variant_durations: dict[tuple[str, ...], list[float]] = defaultdict(list)
        case_durations: list[float] = []
        for case_id, raw_trace in sorted(traces.items()):
            trace = sorted(raw_trace, key=lambda value: (value.occurred_at, value.source_event_id, value.activity))
            if not trace:
                continue
            variant = tuple(event.activity for event in trace)
            variants[variant] += 1
            case_duration = max(0.0, (trace[-1].occurred_at - trace[0].occurred_at).total_seconds())
            variant_durations[variant].append(case_duration)
            case_durations.append(case_duration)
            for source, target in zip(trace, trace[1:]):
                key = (source.activity, target.activity)
                transition_durations[key].append(max(0.0, (target.occurred_at - source.occurred_at).total_seconds()))
                transition_cases[key].add(case_id)
                if target.resource:
                    transition_resources[key][target.resource] += 1
        if not case_durations:
            raise InvalidAdapterResult("Bottleneck analysis requires traces")
        ranked = sorted(transition_durations, key=lambda key: (-_percentile(transition_durations[key], 0.95), key))
        findings: list[Mapping[str, object]] = []
        for rank, key in enumerate(ranked, 1):
            values = transition_durations[key]
            median = statistics.median(values)
            resources = transition_resources[key]
            top_resource, top_count = resources.most_common(1)[0] if resources else ("", 0)
            cases = len(transition_cases[key])
            findings.append(
                {
                    "from_activity": key[0],
                    "to_activity": key[1],
                    "avg_duration_seconds": Decimal(str(round(statistics.mean(values), 2))),
                    "median_duration_seconds": Decimal(str(round(median, 2))),
                    "p95_duration_seconds": Decimal(str(round(_percentile(values, 0.95), 2))),
                    "case_count": cases,
                    "severity": _severity(median, _percentile(values, 0.95)),
                    "resource_bottleneck": top_resource if cases and top_count / cases > 0.5 else "",
                    "rank": rank,
                }
            )
        total = sum(variants.values())
        happy = sorted(variants, key=lambda value: (-variants[value], value))[0]
        rows: list[Mapping[str, object]] = []
        grouped_count = 0
        grouped_weighted_duration = 0.0
        for activities, count in sorted(variants.items(), key=lambda item: (-item[1], item[0])):
            percentage = count * 100 / total
            duration = statistics.mean(variant_durations[activities])
            if percentage < 1:
                grouped_count += count
                grouped_weighted_duration += duration * count
                continue
            key = hashlib.sha256("\0".join(activities).encode()).hexdigest()
            rows.append({"variant_key": key, "activities": list(activities), "case_count": count, "percentage": Decimal(str(round(percentage, 4))), "avg_duration_seconds": Decimal(str(round(duration, 2))), "is_happy_path": activities == happy, "is_grouped_other": False})
        if grouped_count:
            rows.append({"variant_key": hashlib.sha256(b"__other__").hexdigest(), "activities": ["Other variants"], "case_count": grouped_count, "percentage": Decimal(str(round(grouped_count * 100 / total, 4))), "avg_duration_seconds": Decimal(str(round(grouped_weighted_duration / grouped_count, 2))), "is_happy_path": False, "is_grouped_other": True})
        return BottleneckResult(tuple(findings), tuple(rows), total, Decimal(str(round(statistics.mean(case_durations), 2))))


def _event_row(event: CanonicalEvent) -> dict[str, object]:
    return {
        "case_id": event.case_id,
        "activity": event.activity,
        "occurred_at": event.occurred_at.isoformat(),
        "resource": event.resource,
        "source_module": event.source_module,
        "source_event_id": event.source_event_id,
        "attributes": dict(sorted(event.attributes.items())),
    }


class CSVExportFormatter:
    metadata = AdapterMetadata("process_mining.csv", "1.0", "1.0.0", ("export", "csv"))
    content_type = "text/csv"
    extension = "csv"

    def write(self, events: Iterable[CanonicalEvent], destination: TextIO) -> int:
        writer = csv.DictWriter(destination, fieldnames=("case_id", "activity", "occurred_at", "resource", "source_module", "source_event_id", "attributes"), lineterminator="\n")
        writer.writeheader()
        count = 0
        for event in events:
            row = _event_row(event)
            row["attributes"] = json.dumps(row["attributes"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            writer.writerow(row)
            count += 1
        return count


class JSONExportFormatter:
    metadata = AdapterMetadata("process_mining.json", "1.0", "1.0.0", ("export", "json"))
    content_type = "application/json"
    extension = "json"

    def write(self, events: Iterable[CanonicalEvent], destination: TextIO) -> int:
        count = 0
        destination.write("[")
        for event in events:
            if count:
                destination.write(",")
            destination.write(json.dumps(_event_row(event), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            count += 1
        destination.write("]\n")
        return count


class XESExportFormatter:
    metadata = AdapterMetadata("process_mining.xes", "1.0", "1.0.0", ("export", "xes", "ieee-1849-2016"))
    content_type = "application/xml"
    extension = "xes"

    def write(self, events: Iterable[CanonicalEvent], destination: TextIO) -> int:
        root = Element("log", {"xes.version": "1.0", "xes.features": "nested-attributes", "xmlns": "http://www.xes-standard.org/"})
        grouped: dict[str, list[CanonicalEvent]] = defaultdict(list)
        for event in events:
            grouped[event.case_id].append(event)
        count = 0
        for case_id, trace_events in sorted(grouped.items()):
            trace = SubElement(root, "trace")
            SubElement(trace, "string", {"key": "concept:name", "value": case_id})
            for event in sorted(trace_events, key=lambda value: (value.occurred_at, value.source_event_id, value.activity)):
                element = SubElement(trace, "event")
                SubElement(element, "string", {"key": "concept:name", "value": event.activity})
                SubElement(element, "date", {"key": "time:timestamp", "value": event.occurred_at.isoformat()})
                if event.resource:
                    SubElement(element, "string", {"key": "org:resource", "value": event.resource})
                SubElement(element, "string", {"key": "saraise:source", "value": event.source_module})
                count += 1
        destination.write(tostring(root, encoding="unicode", xml_declaration=True))
        destination.write("\n")
        return count


LOCAL_ADAPTERS = (
    CanonicalEventSource(),
    DirectlyFollowsMiner(),
    HeuristicMiner(),
    InductiveMiner(),
    TokenReplayConformance(),
    TransitionDurationAnalyzer(),
    CSVExportFormatter(),
    JSONExportFormatter(),
    XESExportFormatter(),
)
_registered = False


def register_local_adapters() -> None:
    global _registered
    if _registered:
        return
    for adapter in LOCAL_ADAPTERS:
        registry.register(adapter)
    _registered = True


def canonical_events(rows: Iterable[object]) -> list[CanonicalEvent]:
    return [
        CanonicalEvent(
            case_id=str(getattr(row, "case_id")),
            activity=str(getattr(row, "activity")),
            occurred_at=getattr(row, "occurred_at"),
            resource=str(getattr(row, "resource") or ""),
            source_module=str(getattr(row, "source_module")),
            source_event_id=str(getattr(row, "source_event_id") or ""),
            attributes=getattr(row, "attributes") or {},
        )
        for row in rows
    ]


def deterministic_text(formatter: ExportFormatter, events: Iterable[CanonicalEvent]) -> tuple[str, int]:
    destination = io.StringIO(newline="")
    count = formatter.write(events, destination)
    return destination.getvalue(), count


__all__ = [
    "AdapterMetadata", "AdapterRegistry", "BottleneckAlgorithm", "BottleneckResult", "CSVExportFormatter",
    "CanonicalEvent", "CanonicalEventSource", "CapabilityUnavailable", "ConformanceAlgorithm", "ConformanceResult",
    "DirectlyFollowsMiner", "DuplicateAdapterError", "EventSourceAdapter", "ExportFormatter", "HeuristicMiner",
    "InductiveMiner", "InsightProvider", "InvalidAdapterResult", "JSONExportFormatter", "MiningAlgorithm",
    "TokenReplayConformance", "TransitionDurationAnalyzer", "XESExportFormatter", "canonical_events",
    "deterministic_text", "register_local_adapters", "registry",
]
