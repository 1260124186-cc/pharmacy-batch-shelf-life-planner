"""Input contract and shared exceptions for the pharmacy lot planner."""


class PlanningError(ValueError):
    """Raised when an instance cannot produce a valid minimum-cost plan."""


INSTANCE_KEYS = {
    "instance_id",
    "batch_size",
    "shelf_life_shifts",
    "run_cost_cents",
    "waste_cost_cents",
    "changeover_cost_cents",
    "shifts",
}
SHIFT_KEYS = {"index", "demand", "capacity"}
DEMAND_KEYS = {"A", "B"}


def _integer(value, label, minimum=0):
    """Return a JSON integer while rejecting booleans and non-integers."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlanningError(f"{label} must be an integer")
    if value < minimum:
        raise PlanningError(f"{label} must be at least {minimum}")
    return value


def validate_instance(instance):
    """Validate the complete planning instance and return a normalized copy."""
    if not isinstance(instance, dict):
        raise PlanningError("instance must be a JSON object")
    if set(instance) != INSTANCE_KEYS:
        raise PlanningError("instance fields do not match the required schema")

    identifier = instance["instance_id"]
    if not isinstance(identifier, str) or not identifier.strip():
        raise PlanningError("instance_id must be a non-empty string")

    batch_size = _integer(instance["batch_size"], "batch_size", 1)
    shelf_life = _integer(instance["shelf_life_shifts"], "shelf_life_shifts", 1)
    run_cost = _integer(instance["run_cost_cents"], "run_cost_cents")
    waste_cost = _integer(instance["waste_cost_cents"], "waste_cost_cents")
    changeover_cost = _integer(
        instance["changeover_cost_cents"],
        "changeover_cost_cents",
    )
    if batch_size > 12:
        raise PlanningError("batch_size must not exceed 12")
    if shelf_life > 6:
        raise PlanningError("shelf_life_shifts must not exceed 6")

    shifts = instance["shifts"]
    if not isinstance(shifts, list) or not 1 <= len(shifts) <= 12:
        raise PlanningError("shifts must contain between 1 and 12 rows")

    normalized = []
    for position, row in enumerate(shifts):
        if not isinstance(row, dict) or set(row) != SHIFT_KEYS:
            raise PlanningError(f"shifts[{position}] fields do not match the schema")
        index = _integer(row["index"], f"shifts[{position}].index")
        if index != position:
            raise PlanningError("shift indexes must be contiguous and start at zero")
        demand = row["demand"]
        if not isinstance(demand, dict) or set(demand) != DEMAND_KEYS:
            raise PlanningError(
                f"shifts[{position}].demand must contain exactly A and B"
            )
        demand_a = _integer(
            demand["A"],
            f"shifts[{position}].demand.A",
        )
        demand_b = _integer(
            demand["B"],
            f"shifts[{position}].demand.B",
        )
        capacity = _integer(row["capacity"], f"shifts[{position}].capacity")
        if demand_a > 30 or demand_b > 30:
            raise PlanningError(
                f"shifts[{position}] demand per product must not exceed 30"
            )
        if capacity > 3:
            raise PlanningError(f"shifts[{position}].capacity must not exceed 3")
        normalized.append(
            {
                "index": index,
                "demand": {"A": demand_a, "B": demand_b},
                "capacity": capacity,
            }
        )

    return {
        "instance_id": identifier.strip(),
        "batch_size": batch_size,
        "shelf_life_shifts": shelf_life,
        "run_cost_cents": run_cost,
        "waste_cost_cents": waste_cost,
        "changeover_cost_cents": changeover_cost,
        "shifts": normalized,
    }
