"""Exact dynamic programming for two-product, storage-limited batch runs."""

from .model import PlanningError, validate_instance


def _consume(fresh, used, demand):
    """Consume one SKU using FIFO, then defer the second use as long as possible."""
    fresh = list(fresh)
    used = list(used)
    unmet = demand
    discarded = 0
    for offset in range(len(fresh)):
        if unmet:
            take = min(fresh[offset], unmet)
            fresh[offset] -= take
            unmet -= take
            if take and fresh[offset]:
                used[offset] += fresh[offset]
                fresh[offset] = 0
        if unmet:
            take = min(used[offset], unmet)
            used[offset] -= take
            unmet -= take
            if take and used[offset]:
                discarded += used[offset]
                used[offset] = 0
    return tuple(fresh), tuple(used), discarded, unmet


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

    empty = (0,) * shelf_life
    states = {(empty, empty, empty, empty): (0, ())}
    for shift in shifts:
        demand_a = shift["demand"]["A"]
        demand_b = shift["demand"]["B"]
        capacity = shift["capacity"]
        next_states = {}
        for state, (cost, path) in states.items():
            fresh_a, used_a, fresh_b, used_b = state
            for runs_a in range(capacity + 1):
                for runs_b in range(capacity - runs_a + 1):
                    next_fresh_a = list(fresh_a)
                    next_used_a = list(used_a)
                    next_fresh_b = list(fresh_b)
                    next_used_b = list(used_b)

                    next_fresh_a[-1] += runs_a * batch_size
                    next_fresh_b[-1] += runs_b * batch_size
                    fresh_a_after, used_a_after, discarded_a, unmet_a = _consume(
                        next_fresh_a,
                        next_used_a,
                        demand_a,
                    )
                    fresh_b_after, used_b_after, discarded_b, unmet_b = _consume(
                        next_fresh_b,
                        next_used_b,
                        demand_b,
                    )
                    if unmet_a or unmet_b:
                        continue

                    expired = fresh_a_after[0] + used_a_after[0]
                    expired += fresh_b_after[0] + used_b_after[0]
                    discarded = discarded_a + discarded_b + expired
                    next_state = (
                        fresh_a_after[1:] + (0,),
                        used_a_after[1:] + (0,),
                        fresh_b_after[1:] + (0,),
                        used_b_after[1:] + (0,),
                    )
                    stored = sum(next_state[0]) + sum(next_state[1])
                    stored += sum(next_state[2]) + sum(next_state[3])
                    if stored > storage_capacity:
                        continue

                    next_cost = cost + (runs_a + runs_b) * run_cost
                    next_cost += discarded * waste_cost
                    if runs_a and runs_b:
                        next_cost += changeover_cost
                    candidate = (next_cost, path + ((runs_a, runs_b),))
                    known = next_states.get(next_state)
                    if known is None or candidate < known:
                        next_states[next_state] = candidate
        if not next_states:
            raise PlanningError("demand cannot be covered within the shelf window")
        states = next_states

    best = None
    for state, (cost, path) in states.items():
        leftover = sum(state[0]) + sum(state[1]) + sum(state[2]) + sum(state[3])
        candidate = (cost + leftover * waste_cost, path)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise PlanningError("no feasible preparation plan exists")
    return [
        {"shift": index, "A": runs_a, "B": runs_b}
        for index, (runs_a, runs_b) in enumerate(best[1])
    ]
