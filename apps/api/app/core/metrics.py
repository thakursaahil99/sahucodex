"""Prometheus metrics. Each app instance owns its registry so tests can build many apps."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.process_collector import ProcessCollector


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        ProcessCollector(registry=self.registry)
        self.http_requests = Counter(
            "sahucodex_http_requests_total",
            "HTTP requests handled",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "sahucodex_http_request_duration_seconds",
            "HTTP request latency",
            ["method", "route"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
