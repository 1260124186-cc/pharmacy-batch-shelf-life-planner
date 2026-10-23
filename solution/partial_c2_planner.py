"""Feasible two-product greedy planner used for the C2 quality experiment."""

from .expander import expand_plan
from .model import validate_instance


def plan_instance(instance):
    """Build a feasible but not necessarily minimum-cost schedule."""
    data = validate_instance(instance)
    batch_size = data["batch_size"]
    shelf_life = data["shelf_life_shifts"]
    runs = []
    inventory = {"A": [], "B": []}
    for shift in data["shifts"]:
        capacity = shift["capacity"]
        count_a = 0
        count_b = 0
        for sku in ("A", "B"):
            available = sum(
                batch["doses"]
                for batch in inventory[sku]
                if batch["expiry"] >= shift["index"]
            )
            needed = max(0, shift["demand"][sku] - available)
            requested = (needed + batch_size - 1) // batch_size
            if sku == "A":
                count_a = min(capacity, requested)
            else:
                count_b = min(capacity - count_a, requested)
        if count_a * batch_size < shift["demand"]["A"] and not inventory["A"]:
            raise ValueError("greedy schedule cannot cover demand A")
        if count_b * batch_size < shift["demand"]["B"] and not inventory["B"]:
            raise ValueError("greedy schedule cannot cover demand B")
        runs.append({"shift": shift["index"], "A": count_a, "B": count_b})
        for sku, count in (("A", count_a), ("B", count_b)):
            if count:
                inventory[sku].append(
                    {
                        "expiry": shift["index"] + shelf_life - 1,
                        "doses": count * batch_size,
                    }
                )
            unmet = shift["demand"][sku]
            for batch in inventory[sku]:
                if unmet == 0:
                    break
                use = min(batch["doses"], unmet)
                batch["doses"] -= use
                unmet -= use
            if unmet:
                raise ValueError("greedy schedule cannot cover demand")
            inventory[sku] = [
                batch
                for batch in inventory[sku]
                if batch["expiry"] > shift["index"]
            ]
    return expand_plan(data, runs)
