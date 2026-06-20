"""In-process product-KPI metrics registry (PRD §21, NFR-009).

Tracks the four product KPIs the PRD measures the system against:

1. token reduction % vs. standard RAG (PRD target >40% / >60%),
2. answer accuracy on structured docs (PRD target >80% / >90%),
3. routing latency in ms (PRD target <400ms / <200ms),
4. fallback rate from router uncertainty (PRD target <20% / <10%).

The registry is a dependency-free, thread-safe accumulator that exposes a
plain-text exposition compatible with Prometheus-style scrapers via the
``/metrics`` endpoint. It is deliberately lightweight: real production
deployments wire LangSmith for traces and may add a full Prometheus client,
but this gives every deployment a zero-dependency KPI surface out of the box.

Recording is best-effort and must never raise into a request path; callers
observe a metric and move on.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class _Accumulator:
    """Running count/sum for one averaged metric.

    Attributes:
        count: Number of observations recorded.
        total: Sum of observed values.
    """

    count: int = 0
    total: float = 0.0

    def observe(self, value: float) -> None:
        """Record one observation.

        Args:
            value: The observed value to add to the running sum.
        """
        self.count += 1
        self.total += value

    @property
    def average(self) -> float:
        """Return the mean of all observations, or 0.0 when empty.

        Returns:
            The arithmetic mean, or 0.0 if no observation has been recorded.
        """
        if self.count == 0:
            return 0.0
        return self.total / self.count


@dataclass
class ProductMetrics:
    """Thread-safe registry of the four product KPIs.

    Attributes:
        token_reduction: Accumulator of per-query token-reduction fractions.
        answer_accuracy: Accumulator of per-answer accuracy scores (0.0-1.0).
        routing_latency_ms: Accumulator of router latencies in milliseconds.
        routing_total: Count of routing decisions made.
        fallback_total: Count of routing decisions that fell back.
    """

    token_reduction: _Accumulator = field(default_factory=_Accumulator)
    answer_accuracy: _Accumulator = field(default_factory=_Accumulator)
    routing_latency_ms: _Accumulator = field(default_factory=_Accumulator)
    routing_total: int = 0
    fallback_total: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_routing(
        self,
        latency_ms: float,
        fallback: bool,
        token_reduction: float | None = None,
    ) -> None:
        """Record a single routing decision and its KPI signals.

        Args:
            latency_ms: Router latency for the decision, in milliseconds.
            fallback: Whether the router fell back to full-document retrieval.
            token_reduction: Optional token-reduction fraction (0.0-1.0) for
                the decision; omitted when not computable.
        """
        with self._lock:
            self.routing_total += 1
            self.routing_latency_ms.observe(latency_ms)
            if fallback:
                self.fallback_total += 1
            if token_reduction is not None:
                self.token_reduction.observe(token_reduction)

    def record_answer_accuracy(self, score: float) -> None:
        """Record one answer-accuracy evaluation result.

        Args:
            score: Accuracy score in the range 0.0-1.0 for one evaluated answer.
        """
        with self._lock:
            self.answer_accuracy.observe(score)

    @property
    def fallback_rate(self) -> float:
        """Return the fraction of routing decisions that fell back.

        Returns:
            fallback_total / routing_total, or 0.0 when no routing has occurred.
        """
        with self._lock:
            if self.routing_total == 0:
                return 0.0
            return self.fallback_total / self.routing_total

    def render_prometheus(self) -> str:
        """Render the KPIs in Prometheus text exposition format.

        Returns:
            A newline-terminated metrics document suitable for a scraper. Each
            metric carries a HELP and TYPE header per the exposition format.
        """
        with self._lock:
            token_reduction_avg = self.token_reduction.average
            accuracy_avg = self.answer_accuracy.average
            latency_avg = self.routing_latency_ms.average
            routing_total = self.routing_total
            fallback_total = self.fallback_total
            fallback_rate = fallback_total / routing_total if routing_total > 0 else 0.0

        lines = [
            "# HELP rag_token_reduction_ratio Avg token-reduction fraction vs full-doc RAG.",
            "# TYPE rag_token_reduction_ratio gauge",
            f"rag_token_reduction_ratio {token_reduction_avg}",
            "# HELP rag_answer_accuracy_ratio Average evaluated answer-accuracy score.",
            "# TYPE rag_answer_accuracy_ratio gauge",
            f"rag_answer_accuracy_ratio {accuracy_avg}",
            "# HELP rag_routing_latency_ms Average router latency in milliseconds.",
            "# TYPE rag_routing_latency_ms gauge",
            f"rag_routing_latency_ms {latency_avg}",
            "# HELP rag_routing_total Total routing decisions made.",
            "# TYPE rag_routing_total counter",
            f"rag_routing_total {routing_total}",
            "# HELP rag_fallback_total Total routing decisions that fell back.",
            "# TYPE rag_fallback_total counter",
            f"rag_fallback_total {fallback_total}",
            "# HELP rag_fallback_rate Fraction of routing decisions that fell back.",
            "# TYPE rag_fallback_rate gauge",
            f"rag_fallback_rate {fallback_rate}",
        ]
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Reset all accumulators and counters to their empty state."""
        with self._lock:
            self.token_reduction = _Accumulator()
            self.answer_accuracy = _Accumulator()
            self.routing_latency_ms = _Accumulator()
            self.routing_total = 0
            self.fallback_total = 0


_METRICS = ProductMetrics()


def get_metrics() -> ProductMetrics:
    """Return the process-wide product-metrics registry.

    Returns:
        The singleton :class:`ProductMetrics` instance shared across the app.
    """
    return _METRICS
