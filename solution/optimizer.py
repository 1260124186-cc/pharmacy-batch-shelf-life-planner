"""Exact dynamic programming for two-product, capacity-limited batch runs."""

from .model import PlanningError, validate_instance


def optimize_runs(instance):
    """Return per-shift A/B run counts with lexicographic tie-breaking."""
    data = validate_instance(instance)
    batch_size = data["batch_size"]
    shelf_life = data["shelf_life_shifts"]
    run_cost = data["run_cost_cents"]
    waste_cost = data["waste_cost_cents"]
    changeover_cost = data["changeover_cost_cents"]
    storage_capacity = data["storage_capacity_doses"]
    shifts = data["shifts"]

    # State entries are doses by remaining usable shifts. Zero means the doses
    # expire at the end of the current shift.
    empty = (0,) * shelf_life
    states = {(empty, empty): (0, ())}
    for shift in shifts:
        demand_a = shift["demand"]["A"]
        demand_b = shift["demand"]["B"]
        capacity = shift["capacity"]
        next_states = {}
        for (inventory_a, inventory_b), (cost, path) in states.items():
            for runs_a in range(capacity + 1):
                for runs_b in range(capacity - runs_a + 1):
                    buckets_a = list(inventory_a)
                    buckets_b = list(inventory_b)
                    buckets_a[-1] += runs_a * batch_size
                    buckets_b[-1] += runs_b * batch_size

                    unmet_a = demand_a
                    unmet_b = demand_b
                    for offset in range(shelf_life):
                        if unmet_a:
                            used = min(buckets_a[offset], unmet_a)
                            buckets_a[offset] -= used
                            unmet_a -= used
                        if unmet_b:
                            used = min(buckets_b[offset], unmet_b)
                            buckets_b[offset] -= used
                            unmet_b -= used
                    if unmet_a or unmet_b:
                        continue

                    expired = buckets_a[0] + buckets_b[0]
                    next_cost = cost + (runs_a + runs_b) * run_cost
                    next_cost += expired * waste_cost
                    if runs_a and runs_b:
                        next_cost += changeover_cost
                    next_state = (
                        tuple(buckets_a[1:]) + (0,),
                        tuple(buckets_b[1:]) + (0,),
                    )
                    stored = sum(next_state[0]) + sum(next_state[1])
                    if stored > storage_capacity:
                        continue
                    candidate = (next_cost, path + ((runs_a, runs_b),))
                    known = next_states.get(next_state)
                    if known is None or candidate < known:
                        next_states[next_state] = candidate
        if not next_states:
            raise PlanningError("demand cannot be covered within the shelf window")
        states = next_states

    best = None
    for (inventory_a, inventory_b), (cost, path) in states.items():
        leftover = sum(inventory_a) + sum(inventory_b)
        candidate = (cost + leftover * waste_cost, path)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise PlanningError("no feasible preparation plan exists")
    return [
        {"shift": index, "A": runs_a, "B": runs_b}
        for index, (runs_a, runs_b) in enumerate(best[1])
    ]
