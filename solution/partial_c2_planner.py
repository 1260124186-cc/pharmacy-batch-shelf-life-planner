"""Feasible current-shift greedy planner used for the C2 quality experiment."""

from .expander import expand_plan
from .model import validate_instance


def plan_instance(instance):
    """Build a feasible but not necessarily minimum-cost schedule."""
    data = validate_instance(instance)
    runs = []
    unused = []
    for shift in data["shifts"]:
        available = sum(
            batch["doses"]
            for batch in unused
            if batch["expiry"] >= shift["index"]
        )
        needed = max(0, shift["demand"] - available)
        count = min(
            shift["capacity"],
            (needed + data["batch_size"] - 1) // data["batch_size"],
        )
        runs.append(count)
        produced = count * data["batch_size"]
        if produced:
            unused.append(
                {
                    "expiry": shift["index"] + data["shelf_life_shifts"] - 1,
                    "doses": produced,
                }
            )
        unmet = shift["demand"]
        for batch in unused:
            if unmet == 0:
                break
            use = min(batch["doses"], unmet)
            batch["doses"] -= use
            unmet -= use
        if unmet:
            raise ValueError("greedy schedule cannot cover demand")
        unused = [
            batch for batch in unused if batch["expiry"] > shift["index"]
        ]
    return expand_plan(data, runs)
