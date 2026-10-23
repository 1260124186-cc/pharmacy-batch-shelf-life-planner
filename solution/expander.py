"""Expand run counts into deterministic FIFO allocations and cost totals."""

from .model import PlanningError, validate_instance


def expand_plan(instance, run_counts):
    """Expand two-product run counts with independent FIFO inventories."""
    data = validate_instance(instance)
    batch_size = data["batch_size"]
    shelf_life = data["shelf_life_shifts"]
    run_cost = data["run_cost_cents"]
    waste_cost = data["waste_cost_cents"]
    changeover_cost = data["changeover_cost_cents"]
    storage_capacity = data["storage_capacity_doses"]
    shifts = data["shifts"]
    count = len(shifts)

    if not isinstance(run_counts, list) or len(run_counts) != count:
        raise PlanningError("run_counts must have one entry per shift")
    normalized_counts = []
    for index, row in enumerate(run_counts):
        if not isinstance(row, dict) or set(row) != {"shift", "A", "B"}:
            raise PlanningError("run_counts rows do not match the schema")
        if row["shift"] != index:
            raise PlanningError("run_counts shifts must be contiguous")
        runs_a = row["A"]
        runs_b = row["B"]
        if (
            isinstance(runs_a, bool)
            or isinstance(runs_b, bool)
            or not isinstance(runs_a, int)
            or not isinstance(runs_b, int)
        ):
            raise PlanningError("run_counts entries must be integers")
        if runs_a < 0 or runs_b < 0:
            raise PlanningError("run_counts entries must be non-negative")
        if runs_a + runs_b > shifts[index]["capacity"]:
            raise PlanningError("run_counts exceeds shift capacity")
        normalized_counts.append((runs_a, runs_b))

    inventory = []
    allocations = []
    used = {("A", index): 0 for index in range(count)}
    wasted = {("A", index): 0 for index in range(count)}
    used.update({("B", index): 0 for index in range(count)})
    wasted.update({("B", index): 0 for index in range(count)})

    for shift in shifts:
        index = shift["index"]
        runs_a, runs_b = normalized_counts[index]
        for sku, runs in (("A", runs_a), ("B", runs_b)):
            if runs:
                inventory.append(
                    {
                        "production_shift": index,
                        "sku": sku,
                        "expiry_shift": index + shelf_life - 1,
                        "doses": runs * batch_size,
                        "uses": 0,
                    }
                )

        inventory.sort(
            key=lambda row: (
                row["expiry_shift"],
                row["production_shift"],
                row["sku"],
            )
        )
        for sku in ("A", "B"):
            unmet = shift["demand"][sku]
            for bucket in inventory:
                if unmet == 0:
                    break
                if bucket["sku"] != sku:
                    continue
                if bucket["expiry_shift"] < index:
                    raise PlanningError("expired doses remained available")
                doses = min(bucket["doses"], unmet)
                if doses:
                    allocations.append(
                        {
                            "production_shift": bucket["production_shift"],
                            "sku": sku,
                            "use_shift": index,
                            "doses": doses,
                        }
                    )
                    bucket["doses"] -= doses
                    used[(sku, bucket["production_shift"])] += doses
                    unmet -= doses
                    if bucket["uses"] == 0:
                        if bucket["doses"]:
                            bucket["uses"] = 1
                    elif bucket["doses"]:
                        key = (sku, bucket["production_shift"])
                        wasted[key] += bucket["doses"]
                        bucket["doses"] = 0
            if unmet:
                raise PlanningError("selected run counts leave demand uncovered")

        remaining = []
        for bucket in inventory:
            if bucket["expiry_shift"] == index:
                key = (bucket["sku"], bucket["production_shift"])
                wasted[key] += bucket["doses"]
            else:
                remaining.append(bucket)
        inventory = remaining
        if sum(bucket["doses"] for bucket in inventory) > storage_capacity:
            raise PlanningError("storage capacity is exceeded")

    for bucket in inventory:
        key = (bucket["sku"], bucket["production_shift"])
        wasted[key] += bucket["doses"]

    production = []
    for shift in shifts:
        index = shift["index"]
        runs_a, runs_b = normalized_counts[index]
        for sku, runs in (("A", runs_a), ("B", runs_b)):
            produced = runs * batch_size
            used_doses = used[(sku, index)]
            wasted_doses = wasted[(sku, index)]
            if produced != used_doses + wasted_doses:
                raise PlanningError("production accounting does not balance")
            production.append(
                {
                    "production_shift": index,
                    "sku": sku,
                    "runs": runs,
                    "produced_doses": produced,
                    "used_doses": used_doses,
                    "wasted_doses": wasted_doses,
                }
            )

    allocations.sort(
        key=lambda row: (
            row["production_shift"],
            row["sku"],
            row["use_shift"],
        )
    )
    total_runs = sum(runs_a + runs_b for runs_a, runs_b in normalized_counts)
    total_wasted = sum(wasted.values())
    total_changeovers = sum(
        1 for runs_a, runs_b in normalized_counts if runs_a and runs_b
    )
    total_cost = (
        total_runs * run_cost
        + total_wasted * waste_cost
        + total_changeovers * changeover_cost
    )
    return {
        "instance_id": data["instance_id"],
        "run_counts": [
            {"shift": index, "A": runs_a, "B": runs_b}
            for index, (runs_a, runs_b) in enumerate(normalized_counts)
        ],
        "production": production,
        "allocations": allocations,
        "total_runs": total_runs,
        "total_produced_doses": total_runs * batch_size,
        "total_wasted_doses": total_wasted,
        "total_changeovers": total_changeovers,
        "total_cost_cents": total_cost,
    }
