"""Exact dynamic programming for capacity- and shelf-limited batch runs."""

from .model import PlanningError, validate_instance


def optimize_runs(instance):
    """Return the minimum-cost run-count vector with lexicographic tie-breaking."""
    data = validate_instance(instance)
    batch_size = data["batch_size"]
    shelf_life = data["shelf_life_shifts"]
    run_cost = data["run_cost_cents"]
    waste_cost = data["waste_cost_cents"]
    shifts = data["shifts"]

    # State entries are doses by remaining usable shifts. Zero means the doses
    # expire at the end of the current shift.
    states = {(0,) * shelf_life: (0, ())}
    for shift in shifts:
        demand = shift["demand"]
        capacity = shift["capacity"]
        next_states = {}
        for inventory, (cost, path) in states.items():
            for runs in range(capacity + 1):
                buckets = list(inventory)
                buckets[-1] += runs * batch_size
                unmet = demand
                for offset in range(shelf_life):
                    if unmet == 0:
                        break
                    used = min(buckets[offset], unmet)
                    buckets[offset] -= used
                    unmet -= used
                if unmet:
                    continue
                expired = buckets[0]
                next_cost = cost + runs * run_cost + expired * waste_cost
                next_inventory = tuple(buckets[1:]) + (0,)
                candidate = (next_cost, path + (runs,))
                known = next_states.get(next_inventory)
                if known is None or candidate < known:
                    next_states[next_inventory] = candidate
        if not next_states:
            raise PlanningError("demand cannot be covered within the shelf window")
        states = next_states

    best = None
    for inventory, (cost, path) in states.items():
        candidate = (cost + sum(inventory) * waste_cost, path)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise PlanningError("no feasible preparation plan exists")
    return list(best[1])
