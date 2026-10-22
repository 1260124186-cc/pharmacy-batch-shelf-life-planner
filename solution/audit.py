"""Recompute the canonical plan and audit a submitted result."""

from .expander import expand_plan
from .optimizer import optimize_runs


def audit_plan(instance, plan):
    """Compare a submitted plan with an independently recomputed optimum."""
    minimum = expand_plan(instance, optimize_runs(instance))
    actual_cost = None
    if isinstance(plan, dict):
        candidate = plan.get("total_cost_cents")
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            actual_cost = candidate
    valid = plan == minimum
    return {
        "instance_id": minimum["instance_id"],
        "valid": valid,
        "actual_cost_cents": actual_cost,
        "minimum_cost_cents": minimum["total_cost_cents"],
        "reason": "" if valid else "plan does not match the minimum-cost FIFO expansion",
    }
