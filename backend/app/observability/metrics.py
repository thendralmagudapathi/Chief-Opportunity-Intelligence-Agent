"""In-process metrics for latency, cost and drift monitoring."""

from __future__ import annotations

import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass
class MetricSnapshot:
    counters: dict[str, float]
    histograms: dict[str, dict[str, float]]


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=500))

    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms[name].append(value)

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            histograms = {
                name: _summarise(list(values)) for name, values in self._histograms.items()
            }
            return MetricSnapshot(counters=dict(self._counters), histograms=histograms)

    def drift_alerts(self, *, baseline: MetricSnapshot, threshold_ratio: float = 0.25) -> list[str]:
        alerts: list[str] = []
        for name, stats in self.snapshot().histograms.items():
            base = baseline.histograms.get(name, {})
            if "p95" not in stats or "p95" not in base:
                continue
            base_p95 = base["p95"]
            if base_p95 <= 0:
                continue
            delta = (stats["p95"] - base_p95) / base_p95
            if delta > threshold_ratio:
                alerts.append(f"{name} p95 drift {delta:.0%}")
        return alerts


def _summarise(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0.0}
    ordered = sorted(values)
    count = len(ordered)

    def percentile(p: float) -> float:
        index = min(count - 1, max(0, int(p * count) - 1))
        return ordered[index]

    return {
        "count": float(count),
        "mean": statistics.fmean(ordered),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "max": ordered[-1],
    }


registry = MetricsRegistry()


class StageTimer:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self._started = time.perf_counter()

    def finish(self) -> float:
        elapsed_ms = (time.perf_counter() - self._started) * 1000
        registry.observe(f"stage_latency_ms.{self.stage}", elapsed_ms)
        return elapsed_ms
