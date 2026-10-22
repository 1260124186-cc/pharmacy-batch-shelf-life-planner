"""Expand run counts into deterministic FIFO allocations and cost totals."""

from .model import PlanningError, validate_instance


def expand_plan(instance, run_counts):
    """Return the canonical first-expiry-first-out plan for supplied run counts."""
    data = validate_instance(instance)
    batch_size = data["batch_size"]
    shelf_life = data["shelf_life_shifts"]
    run_cost = data["run_cost_cents"]
    waste_cost = data["waste_cost_cents"]
    shifts = data["shifts"]
    count = len(shifts)

    if not isinstance(run_counts, list) or len(run_counts) != count:
        raise PlanningError("run_counts must have one entry per shift")
    for index, runs in enumerate(run_counts):
        if isinstance(runs, bool) or not isinstance(runs, int):
            raise PlanningError("run_counts entries must be integers")
        if not 0 <= runs <= shifts[index]["capacity"]:
            raise PlanningError("run_counts exceeds shift capacity")

    inventory = []
    allocations = []
    used_by_shift = [0] * count
    wasted_by_shift = [0] * count

    for shift in shifts:
        index = shift["index"]
        runs = run_counts[index]
        if runs:
            inventory.append(
                {
                    "production_shift": index,
                    "expiry_shift": index + shelf_life - 1,
                    "doses": runs * batch_size,
                }
            )

        inventory.sort(
            key=lambda row: (row["expiry_shift"], row["production_shift"])
        )
        unmet = shift["demand"]
        for bucket in inventory:
            if unmet == 0:
                break
            if bucket["expiry_shift"] < index:
                raise PlanningError("expired doses remained available")
            doses = min(bucket["doses"], unmet)
            if doses:
                allocations.append(
                    {
                        "production_shift": bucket["production_shift"],
                        "use_shift": index,
                        "doses": doses,
                    }
                )
                bucket["doses"] -= doses
                used_by_shift[bucket["production_shift"]] += doses
                unmet -= doses
        if unmet:
            raise PlanningError("selected run counts leave demand uncovered")

        remaining = []
        for bucket in inventory:
            if bucket["expiry_shift"] == index:
                wasted_by_shift[bucket["production_shift"]] += bucket["doses"]
            else:
                remaining.append(bucket)
        inventory = remaining

    for bucket in inventory:
        wasted_by_shift[bucket["production_shift"]] += bucket["doses"]

    production = []
    for shift in shifts:
        index = shift["index"]
        produced = run_counts[index] * batch_size
        used = used_by_shift[index]
        wasted = wasted_by_shift[index]
        if produced != used + wasted:
            raise PlanningError("production accounting does not balance")
        production.append(
            {
                "production_shift": index,
                "runs": run_counts[index],
                "produced_doses": produced,
                "used_doses": used,
                "wasted_doses": wasted,
            }
        )

    allocations.sort(key=lambda row: (row["production_shift"], row["use_shift"]))
    total_runs = sum(run_counts)
    total_wasted = sum(wasted_by_shift)
    total_cost = total_runs * run_cost + total_wasted * waste_cost
    return {
        "instance_id": data["instance_id"],
        "run_counts": list(run_counts),
        "production": production,
        "allocations": allocations,
        "total_runs": total_runs,
        "total_produced_doses": total_runs * batch_size,
        "total_wasted_doses": total_wasted,
        "total_cost_cents": total_cost,
    }
