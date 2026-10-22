"""Cross-shift preparation planning for short-lived pharmacy batches."""

__all__ = ["PlanningError", "audit_plan", "plan_instance"]

from .model import PlanningError


def audit_plan(instance, plan):
    """Load the audit implementation lazily."""
    from .audit import audit_plan as run_audit

    return run_audit(instance, plan)


def plan_instance(instance):
    """Load the planner implementation lazily."""
    from .planner import plan_instance as run_planner

    return run_planner(instance)
