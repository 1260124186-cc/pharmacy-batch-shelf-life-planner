"""Independent checks for the pharmacy batch shelf-life planner."""

import json
import random
import subprocess
import sys
import tempfile
from itertools import product
from pathlib import Path


WORKSPACE = Path("/workspace")
COMMAND = [sys.executable, "-m", "pharmacy_lots"]


def make_instance(
    demands,
    capacities,
    identifier="test-pharmacy",
    batch_size=5,
    shelf_life=3,
    run_cost=4600,
    waste_cost=95,
):
    """Build a valid instance with contiguous shift indexes."""
    return {
        "instance_id": identifier,
        "batch_size": batch_size,
        "shelf_life_shifts": shelf_life,
        "run_cost_cents": run_cost,
        "waste_cost_cents": waste_cost,
        "shifts": [
            {"index": index, "demand": demand, "capacity": capacity}
            for index, (demand, capacity) in enumerate(
                zip(demands, capacities, strict=True)
            )
        ],
    }


def reference_plan(instance, run_counts):
    """Expand supplied run counts with FIFO ages and exact integer accounting."""
    batch_size = instance["batch_size"]
    shelf_life = instance["shelf_life_shifts"]
    shifts = instance["shifts"]
    inventory = []
    used = [0] * len(shifts)
    wasted = [0] * len(shifts)
    allocations = []

    for shift in shifts:
        index = shift["index"]
        runs = run_counts[index]
        if not 0 <= runs <= shift["capacity"]:
            raise ValueError("capacity")
        if runs:
            inventory.append(
                [index, index + shelf_life - 1, runs * batch_size]
            )
        inventory.sort(key=lambda row: (row[1], row[0]))
        unmet = shift["demand"]
        for row in inventory:
            if unmet == 0:
                break
            doses = min(row[2], unmet)
            if doses:
                allocations.append(
                    {
                        "production_shift": row[0],
                        "use_shift": index,
                        "doses": doses,
                    }
                )
                row[2] -= doses
                used[row[0]] += doses
                unmet -= doses
        if unmet:
            raise ValueError("uncovered")
        remaining = []
        for row in inventory:
            if row[1] == index:
                wasted[row[0]] += row[2]
            else:
                remaining.append(row)
        inventory = remaining

    for row in inventory:
        wasted[row[0]] += row[2]
    production = [
        {
            "production_shift": shift["index"],
            "runs": run_counts[shift["index"]],
            "produced_doses": run_counts[shift["index"]] * batch_size,
            "used_doses": used[shift["index"]],
            "wasted_doses": wasted[shift["index"]],
        }
        for shift in shifts
    ]
    allocations.sort(key=lambda row: (row["production_shift"], row["use_shift"]))
    total_runs = sum(run_counts)
    total_wasted = sum(wasted)
    return {
        "instance_id": instance["instance_id"],
        "run_counts": list(run_counts),
        "production": production,
        "allocations": allocations,
        "total_runs": total_runs,
        "total_produced_doses": total_runs * batch_size,
        "total_wasted_doses": total_wasted,
        "total_cost_cents": (
            total_runs * instance["run_cost_cents"]
            + total_wasted * instance["waste_cost_cents"]
        ),
    }


def brute_force_plan(instance):
    """Find the exact optimum by enumerating every capacity-respecting vector."""
    choices = [
        range(shift["capacity"] + 1)
        for shift in instance["shifts"]
    ]
    best = None
    for runs in product(*choices):
        try:
            candidate = reference_plan(instance, runs)
        except ValueError:
            continue
        key = (candidate["total_cost_cents"], list(runs))
        if best is None or key < (best["total_cost_cents"], best["run_counts"]):
            best = candidate
    if best is None:
        raise ValueError("infeasible")
    return best


def invoke(stage, instance, plan=None):
    """Run the package command and return status, output text, and output path."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        instance_path = root / "instance.json"
        instance_path.write_text(
            json.dumps(instance, ensure_ascii=False),
            encoding="utf-8",
        )
        arguments = [sys.executable, "-m", "pharmacy_lots", stage, str(instance_path)]
        output_path = root / "output.json"
        if stage == "audit":
            plan_path = root / "plan.json"
            plan_path.write_text(
                json.dumps(plan, ensure_ascii=False),
                encoding="utf-8",
            )
            arguments.append(str(plan_path))
        arguments.append(str(output_path))
        completed = subprocess.run(
            arguments,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = output_path.read_text(encoding="utf-8") if output_path.exists() else None
        return completed.returncode, raw


def output(stage, instance, plan=None):
    """Return parsed output for a successful command, or None."""
    status, raw = invoke(stage, instance, plan)
    if status != 0 or raw is None:
        return None
    return json.loads(raw)


def generated_instance(seed, count):
    """Create a reproducible demand/capacity instance with the documented rule."""
    generator = random.Random(seed)
    demands = [
        max(0, generator.randint(0, 8) + (index % 3) - 1)
        for index in range(count)
    ]
    capacities = [1 + (index % 2) for index in range(count)]
    return make_instance(
        demands,
        capacities,
        identifier=f"generated-{seed}",
        batch_size=5,
        shelf_life=3,
        run_cost=4600,
        waste_cost=95,
    )


def second_best_plan(instance):
    """Return a feasible plan strictly above the optimum for audit testing."""
    expected = brute_force_plan(instance)
    choices = [range(shift["capacity"] + 1) for shift in instance["shifts"]]
    alternatives = []
    for runs in product(*choices):
        try:
            candidate = reference_plan(instance, runs)
        except ValueError:
            continue
        if candidate["total_cost_cents"] > expected["total_cost_cents"]:
            alternatives.append(candidate)
    return min(
        alternatives,
        key=lambda row: (row["total_cost_cents"], row["run_counts"]),
    )


def test_c1_single_shift_batch():
    """Cover a small single-shift demand with one fixed batch."""
    instance = make_instance([5], [1], batch_size=5, shelf_life=1, run_cost=100, waste_cost=7)
    expected = reference_plan(instance, [1])
    assert output("run", instance) == expected


def test_c1_shelf_life_and_capacity():
    """Find a feasible optimum when the shelf window is narrower than the horizon."""
    instance = make_instance(
        [0, 7, 0, 6, 0],
        [1, 1, 1, 1, 1],
        batch_size=4,
        shelf_life=2,
        run_cost=10,
        waste_cost=3,
    )
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected


def test_c1_prepare_early_vs_late():
    """Prefer an early batch when a later batch would leave the first demand short."""
    instance = make_instance(
        [1, 0, 4],
        [1, 1, 1],
        batch_size=5,
        shelf_life=3,
        run_cost=10,
        waste_cost=100,
    )
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected


def test_c1_lexicographic_tie():
    """Choose the lexicographically smaller run vector when costs tie."""
    instance = make_instance(
        [5, 0, 5],
        [1, 1, 1],
        batch_size=5,
        shelf_life=2,
        run_cost=0,
        waste_cost=0,
    )
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected
    assert expected["run_counts"] == [1, 0, 1]


def test_c1_infeasible_returns_failure():
    """Reject a demand that cannot fit inside the available shelf window."""
    instance = make_instance(
        [15, 0],
        [1, 0],
        batch_size=5,
        shelf_life=1,
        run_cost=10,
        waste_cost=1,
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        instance_path = root / "instance.json"
        output_path = root / "output.json"
        instance_path.write_text(json.dumps(instance), encoding="utf-8")
        output_path.write_text("keep", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pharmacy_lots",
                "plan",
                str(instance_path),
                str(output_path),
            ],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode != 0
        assert output_path.read_text(encoding="utf-8") == "keep"


def test_c2_fifo_allocations():
    """Use the oldest still-valid batch before a batch prepared later."""
    instance = make_instance(
        [4, 0, 4],
        [1, 1, 1],
        batch_size=5,
        shelf_life=3,
        run_cost=100,
        waste_cost=1,
    )
    actual = output("run", instance)
    assert actual is not None
    assert actual == reference_plan(instance, actual["run_counts"])
    assert any(
        row
        == {
            "production_shift": 0,
            "use_shift": 2,
            "doses": 1,
        }
        for row in actual["allocations"]
    )


def test_c2_expired_doses_counted():
    """Charge unused doses to the expiry shift instead of carrying them forever."""
    instance = make_instance(
        [1, 0, 0, 4],
        [1, 1, 1, 1],
        batch_size=5,
        shelf_life=2,
        run_cost=10,
        waste_cost=1,
    )
    actual = output("run", instance)
    assert actual is not None
    assert actual == reference_plan(instance, actual["run_counts"])
    assert actual["total_wasted_doses"] == 5


def test_c2_zero_demand_tail_waste():
    """Leave a short-lived batch's final doses in the waste account."""
    instance = make_instance(
        [1, 0, 0],
        [1, 1, 1],
        batch_size=5,
        shelf_life=2,
        run_cost=10,
        waste_cost=1,
    )
    actual = output("run", instance)
    assert actual is not None
    assert actual == reference_plan(instance, actual["run_counts"])
    assert actual["total_wasted_doses"] == 4
    assert actual["total_cost_cents"] == 14


def test_c2_plan_accounting_consistent():
    """Keep produced, used, wasted, allocation, and total fields conserved."""
    instance = make_instance(
        [3, 2, 0, 4],
        [1, 2, 1, 1],
        batch_size=5,
        shelf_life=3,
        run_cost=17,
        waste_cost=2,
    )
    actual = output("run", instance)
    assert actual is not None
    expected = reference_plan(instance, actual["run_counts"])
    assert actual == expected
    assert actual["total_produced_doses"] == (
        actual["total_runs"] * instance["batch_size"]
    )
    assert sum(row["used_doses"] for row in actual["production"]) == sum(
        row["doses"] for row in actual["allocations"]
    )


def test_c3_accepts_optimal_plan():
    """Audit a canonical plan built independently from the instance."""
    instance = make_instance(
        [2, 2, 1, 3],
        [1, 1, 1, 1],
        batch_size=5,
        shelf_life=2,
        run_cost=23,
        waste_cost=4,
    )
    expected = brute_force_plan(instance)
    actual = output("audit", instance, expected)
    assert actual == {
        "instance_id": instance["instance_id"],
        "valid": True,
        "actual_cost_cents": expected["total_cost_cents"],
        "minimum_cost_cents": expected["total_cost_cents"],
        "reason": "",
    }


def test_c3_rejects_tampered_cost():
    """Reject a plan whose self-reported total was changed."""
    instance = make_instance(
        [1, 2, 1],
        [1, 1, 1],
        batch_size=5,
        shelf_life=2,
        run_cost=20,
        waste_cost=3,
    )
    expected = brute_force_plan(instance)
    tampered = dict(expected)
    tampered["total_cost_cents"] += 1
    actual = output("audit", instance, tampered)
    assert actual is not None
    assert actual["valid"] is False
    assert actual["minimum_cost_cents"] == expected["total_cost_cents"]


def test_c3_rejects_missing_production():
    """Reject a plan with an incomplete production summary."""
    instance = make_instance(
        [3, 0, 3],
        [1, 1, 1],
        batch_size=5,
        shelf_life=3,
        run_cost=11,
        waste_cost=2,
    )
    expected = brute_force_plan(instance)
    incomplete = dict(expected)
    incomplete["production"] = expected["production"][1:]
    actual = output("audit", instance, incomplete)
    assert actual is not None
    assert actual["valid"] is False


def test_c3_rejects_nonoptimal_run_counts():
    """Reject a feasible schedule that spends more than the exact optimum."""
    instance = make_instance(
        [4, 0, 4],
        [1, 1, 1],
        batch_size=5,
        shelf_life=3,
        run_cost=10,
        waste_cost=1,
    )
    candidate = second_best_plan(instance)
    actual = output("audit", instance, candidate)
    assert actual is not None
    assert actual["valid"] is False


def test_c3_invalid_instance_preserves_output():
    """Reject duplicate shift indexes without touching an existing file."""
    instance = make_instance([1], [1])
    instance["shifts"].append({"index": 0, "demand": 0, "capacity": 1})
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        instance_path = root / "instance.json"
        output_path = root / "output.json"
        instance_path.write_text(json.dumps(instance), encoding="utf-8")
        output_path.write_text("existing", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pharmacy_lots",
                "run",
                str(instance_path),
                str(output_path),
            ],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode != 0
        assert output_path.read_text(encoding="utf-8") == "existing"


def test_e2e_example_instance():
    """Match the bundled example against an independent enumeration."""
    instance = json.loads((WORKSPACE / "example.json").read_text(encoding="utf-8"))
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected


def test_e2e_generated_ten_shift_instance():
    """Handle a longer generated horizon without losing FIFO accounting."""
    instance = generated_instance(20261023, 10)
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected
