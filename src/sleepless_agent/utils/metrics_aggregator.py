"""Metrics aggregation utility for handling multi-phase execution metrics."""

from __future__ import annotations

from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from sleepless_agent.monitoring.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PhaseMetrics:
    """Metrics for a single execution phase."""
    cost_usd: Optional[float] = None
    duration_ms: Optional[int] = None
    turns: Optional[int] = None

    def to_dict(self, prefix: str) -> Dict[str, Optional[Any]]:
        """Convert to dictionary with prefixed keys.

        Args:
            prefix: Prefix for keys (e.g., "planner", "worker", "evaluator")

        Returns:
            Dictionary with keys like "planner_cost_usd", "planner_duration_ms", etc.
        """
        return {
            f"{prefix}_cost_usd": self.cost_usd,
            f"{prefix}_duration_ms": self.duration_ms,
            f"{prefix}_turns": self.turns,
        }

    def update_from_result(self, cost_usd: Optional[float] = None,
                          duration_ms: Optional[int] = None,
                          turns: Optional[int] = None) -> None:
        """Update metrics from execution result.

        Args:
            cost_usd: Cost in USD
            duration_ms: Duration in milliseconds
            turns: Number of API turns
        """
        if cost_usd is not None:
            self.cost_usd = cost_usd
        if duration_ms is not None:
            self.duration_ms = duration_ms
        if turns is not None:
            self.turns = turns


@dataclass
class CombinedMetrics:
    """Combined metrics from all phases."""
    total_cost_usd: float = 0.0
    duration_api_ms: int = 0
    num_turns: int = 0

    def add_phase(self, phase_metrics: PhaseMetrics) -> None:
        """Add metrics from a phase to the combined totals.

        Args:
            phase_metrics: Metrics from a single phase
        """
        if phase_metrics.cost_usd is not None:
            self.total_cost_usd += phase_metrics.cost_usd
        if phase_metrics.duration_ms is not None:
            self.duration_api_ms += phase_metrics.duration_ms
        if phase_metrics.turns is not None:
            self.num_turns += phase_metrics.turns

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "total_cost_usd": self.total_cost_usd,
            "duration_api_ms": self.duration_api_ms,
            "num_turns": self.num_turns,
        }


class MetricsAggregator:
    """Aggregates metrics from multi-phase execution."""

    def __init__(self):
        """Initialize the metrics aggregator."""
        self.planner = PhaseMetrics()
        self.worker = PhaseMetrics()
        self.evaluator = PhaseMetrics()
        self.combined = CombinedMetrics()

    def update_planner(self, cost_usd: Optional[float] = None,
                      duration_ms: Optional[int] = None,
                      turns: Optional[int] = None) -> None:
        """Update planner phase metrics."""
        self.planner.update_from_result(cost_usd, duration_ms, turns)

    def update_worker(self, cost_usd: Optional[float] = None,
                     duration_ms: Optional[int] = None,
                     turns: Optional[int] = None) -> None:
        """Update worker phase metrics."""
        self.worker.update_from_result(cost_usd, duration_ms, turns)

    def update_evaluator(self, cost_usd: Optional[float] = None,
                        duration_ms: Optional[int] = None,
                        turns: Optional[int] = None) -> None:
        """Update evaluator phase metrics."""
        self.evaluator.update_from_result(cost_usd, duration_ms, turns)

    def calculate_combined(self) -> None:
        """Calculate combined metrics from all phases."""
        self.combined = CombinedMetrics()
        self.combined.add_phase(self.planner)
        self.combined.add_phase(self.worker)
        self.combined.add_phase(self.evaluator)

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary.

        Returns:
            Dictionary with all phase metrics and combined metrics
        """
        self.calculate_combined()

        metrics = {}
        metrics.update(self.planner.to_dict("planner"))
        metrics.update(self.worker.to_dict("worker"))
        metrics.update(self.evaluator.to_dict("evaluator"))

        # Add combined metrics (without prefix)
        metrics.update(self.combined.to_dict())

        return metrics

    def get_phase_metrics(self, phase: str) -> PhaseMetrics:
        """Get metrics for a specific phase.

        Args:
            phase: Phase name ("planner", "worker", or "evaluator")

        Returns:
            PhaseMetrics for the specified phase

        Raises:
            ValueError: If phase name is invalid
        """
        phase_map = {
            "planner": self.planner,
            "worker": self.worker,
            "evaluator": self.evaluator,
        }

        if phase not in phase_map:
            raise ValueError(f"Invalid phase: {phase}. Must be one of: {list(phase_map.keys())}")

        return phase_map[phase]