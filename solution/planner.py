"""Compose exact run optimization with canonical FIFO expansion."""

from .expander import expand_plan
from .optimizer import optimize_runs


def plan_instance(instance):
    """Return the complete minimum-cost preparation plan."""
    runs = optimize_runs(instance)
    return expand_plan(instance, runs)
