"""Independent checks for the two-product pharmacy batch planner."""

import copy
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
    batch_size=4,
    shelf_life=3,
    run_cost=100,
    waste_cost=7,
    changeover_cost=30,
    storage_capacity=1000,
):
    """Build an instance whose demand rows contain A and B doses."""
    return {
        "instance_id": identifier,
        "batch_size": batch_size,
        "shelf_life_shifts": shelf_life,
        "run_cost_cents": run_cost,
        "waste_cost_cents": waste_cost,
        "changeover_cost_cents": changeover_cost,
        "storage_capacity_doses": storage_capacity,
        "shifts": [
            {
                "index": index,
                "demand": {"A": demand[0], "B": demand[1]},
                "capacity": capacity,
            }
            for index, (demand, capacity) in enumerate(
                zip(demands, capacities, strict=True)
            )
        ],
    }


def reference_plan(instance, run_counts):
    """Expand counts with separate product inventories and changeover costs."""
    batch_size = instance["batch_size"]
    shelf_life = instance["shelf_life_shifts"]
    storage_capacity = instance["storage_capacity_doses"]
    shifts = instance["shifts"]
    normalized = []
    for index, row in enumerate(run_counts):
        if row["shift"] != index:
            raise ValueError("shift")
        if row["A"] < 0 or row["B"] < 0:
            raise ValueError("negative")
        if row["A"] + row["B"] > shifts[index]["capacity"]:
            raise ValueError("capacity")
        normalized.append((row["A"], row["B"]))

    inventory = []
    allocations = []
    used = {(sku, index): 0 for sku in ("A", "B") for index in range(len(shifts))}
    wasted = {
        (sku, index): 0 for sku in ("A", "B") for index in range(len(shifts))
    }
    for shift in shifts:
        index = shift["index"]
        runs_a, runs_b = normalized[index]
        for sku, runs in (("A", runs_a), ("B", runs_b)):
            if runs:
                inventory.append(
                    [index, sku, index + shelf_life - 1, runs * batch_size]
                )
        inventory.sort(key=lambda row: (row[2], row[0], row[1]))
        for sku in ("A", "B"):
            unmet = shift["demand"][sku]
            for row in inventory:
                if unmet == 0:
                    break
                if row[1] != sku:
                    continue
                doses = min(row[3], unmet)
                if doses:
                    allocations.append(
                        {
                            "production_shift": row[0],
                            "sku": sku,
                            "use_shift": index,
                            "doses": doses,
                        }
                    )
                    row[3] -= doses
                    used[(sku, row[0])] += doses
                    unmet -= doses
            if unmet:
                raise ValueError("uncovered")
        remaining = []
        for row in inventory:
            if row[2] == index:
                wasted[(row[1], row[0])] += row[3]
            else:
                remaining.append(row)
        inventory = remaining
        if sum(row[3] for row in inventory) > storage_capacity:
            raise ValueError("storage")

    for row in inventory:
        wasted[(row[1], row[0])] += row[3]
    production = []
    for shift in shifts:
        index = shift["index"]
        runs_a, runs_b = normalized[index]
        for sku, runs in (("A", runs_a), ("B", runs_b)):
            production.append(
                {
                    "production_shift": index,
                    "sku": sku,
                    "runs": runs,
                    "produced_doses": runs * batch_size,
                    "used_doses": used[(sku, index)],
                    "wasted_doses": wasted[(sku, index)],
                }
            )
    allocations.sort(
        key=lambda row: (
            row["production_shift"],
            row["sku"],
            row["use_shift"],
        )
    )
    total_runs = sum(runs_a + runs_b for runs_a, runs_b in normalized)
    total_wasted = sum(wasted.values())
    total_changeovers = sum(
        1 for runs_a, runs_b in normalized if runs_a and runs_b
    )
    return {
        "instance_id": instance["instance_id"],
        "run_counts": [
            {"shift": index, "A": runs_a, "B": runs_b}
            for index, (runs_a, runs_b) in enumerate(normalized)
        ],
        "production": production,
        "allocations": allocations,
        "total_runs": total_runs,
        "total_produced_doses": total_runs * batch_size,
        "total_wasted_doses": total_wasted,
        "total_changeovers": total_changeovers,
        "total_cost_cents": (
            total_runs * instance["run_cost_cents"]
            + total_wasted * instance["waste_cost_cents"]
            + total_changeovers * instance["changeover_cost_cents"]
        ),
    }


def run_choices(capacity):
    """Return every non-negative A/B run pair that fits one shift."""
    return [
        (runs_a, runs_b)
        for runs_a in range(capacity + 1)
        for runs_b in range(capacity - runs_a + 1)
    ]


def brute_force_plan(instance):
    """Enumerate every capacity-respecting A/B count vector."""
    choices = [
        run_choices(shift["capacity"])
        for shift in instance["shifts"]
    ]
    best = None
    best_key = None
    for vector in product(*choices):
        runs = [
            {"shift": index, "A": pair[0], "B": pair[1]}
            for index, pair in enumerate(vector)
        ]
        try:
            candidate = reference_plan(instance, runs)
        except ValueError:
            continue
        key = (candidate["total_cost_cents"], list(vector))
        if best is None or key < best_key:
            best = candidate
            best_key = key
    if best is None:
        raise ValueError("infeasible")
    return best


def output(stage, instance, plan=None):
    """Run one command and return parsed JSON output on success."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        instance_path = root / "instance.json"
        output_path = root / "output.json"
        instance_path.write_text(
            json.dumps(instance, ensure_ascii=False),
            encoding="utf-8",
        )
        arguments = [
            sys.executable,
            "-m",
            "pharmacy_lots",
            stage,
            str(instance_path),
        ]
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
        if completed.returncode != 0 or not output_path.exists():
            return None
        return json.loads(output_path.read_text(encoding="utf-8"))


def generated_instance(seed, count):
    """Create reproducible A/B demand with a shared per-shift capacity."""
    generator = random.Random(seed)
    demands = []
    capacities = []
    for index in range(count):
        demands.append(
            (
                generator.randint(0, 5),
                max(0, generator.randint(0, 5) + (index % 2)),
            )
        )
        capacities.append(2 if index % 2 == 0 else 1)
    return make_instance(
        demands,
        capacities,
        identifier=f"generated-{seed}",
        batch_size=4,
        shelf_life=3,
        run_cost=3800,
        waste_cost=70,
        changeover_cost=900,
    )


def second_best_plan(instance):
    """Return a feasible vector whose cost is strictly above the optimum."""
    optimum = brute_force_plan(instance)
    choices = [run_choices(shift["capacity"]) for shift in instance["shifts"]]
    alternatives = []
    for vector in product(*choices):
        runs = [
            {"shift": index, "A": pair[0], "B": pair[1]}
            for index, pair in enumerate(vector)
        ]
        try:
            candidate = reference_plan(instance, runs)
        except ValueError:
            continue
        if candidate["total_cost_cents"] > optimum["total_cost_cents"]:
            alternatives.append(candidate)
    return min(
        alternatives,
        key=lambda row: (
            row["total_cost_cents"],
            [(item["A"], item["B"]) for item in row["run_counts"]],
        ),
    )


def test_c1_single_shift_two_products():
    """Produce one run of each product when both are needed immediately."""
    instance = make_instance(
        [(4, 3)],
        [2],
        batch_size=4,
        shelf_life=1,
        run_cost=100,
        waste_cost=7,
        changeover_cost=50,
    )
    expected = brute_force_plan(instance)
    assert output("run", instance) == expected


def test_c1_shared_capacity_and_shelf():
    """Respect a capacity shared by both products across the shelf window."""
    instance = make_instance(
        [(0, 4), (5, 0), (0, 5), (4, 4)],
        [2, 1, 2, 2],
        batch_size=4,
        shelf_life=2,
        run_cost=11,
        waste_cost=3,
        changeover_cost=7,
    )
    assert output("run", instance) == brute_force_plan(instance)


def test_c1_changeover_tradeoff():
    """Pay one changeover only when that shift prepares both products."""
    instance = make_instance(
        [(2, 2), (0, 0), (2, 2)],
        [2, 2, 2],
        batch_size=4,
        shelf_life=2,
        run_cost=10,
        waste_cost=2,
        changeover_cost=100,
    )
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected


def test_c1_lexicographic_pair_tie():
    """Break equal cost by per-shift A then B counts."""
    instance = make_instance(
        [(4, 0), (0, 4)],
        [2, 2],
        batch_size=4,
        shelf_life=4,
        run_cost=0,
        waste_cost=0,
        changeover_cost=0,
    )
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected
    assert [(row["A"], row["B"]) for row in expected["run_counts"]] == [
        (1, 0),
        (0, 1),
    ]


def test_c1_infeasible_shared_capacity():
    """Reject a demand that exceeds the shared shelf window."""
    instance = make_instance(
        [(20, 0), (0, 0)],
        [1, 0],
        batch_size=4,
        shelf_life=1,
        run_cost=10,
        waste_cost=1,
        changeover_cost=3,
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


def test_c2_product_specific_fifo():
    """Keep A and B inventories separate while consuming oldest first."""
    instance = make_instance(
        [(3, 0), (0, 4), (5, 2)],
        [2, 2, 2],
        batch_size=4,
        shelf_life=3,
        run_cost=20,
        waste_cost=1,
        changeover_cost=4,
    )
    actual = output("run", instance)
    assert actual is not None
    assert actual == reference_plan(instance, actual["run_counts"])


def test_c2_changeover_accounting():
    """Charge one changeover for a shift that prepares both products."""
    instance = make_instance(
        [(2, 2), (0, 0)],
        [2, 1],
        batch_size=4,
        shelf_life=1,
        run_cost=10,
        waste_cost=0,
        changeover_cost=7,
    )
    actual = output("run", instance)
    assert actual is not None
    assert actual["run_counts"] == [
        {"shift": 0, "A": 1, "B": 1},
        {"shift": 1, "A": 0, "B": 0},
    ]
    assert actual["total_changeovers"] == 1
    assert actual["total_cost_cents"] == 27


def test_c2_two_product_expiry_waste():
    """Put each product's unused doses into its own waste account."""
    instance = make_instance(
        [(1, 1), (0, 0), (0, 0)],
        [2, 1, 1],
        batch_size=4,
        shelf_life=2,
        run_cost=10,
        waste_cost=1,
        changeover_cost=3,
    )
    actual = output("run", instance)
    assert actual is not None
    assert actual == reference_plan(instance, actual["run_counts"])
    assert actual["total_wasted_doses"] == 6
    assert actual["total_cost_cents"] == 29


def test_c2_plan_accounting_consistent():
    """Keep per-SKU production, allocation, waste, and totals conserved."""
    instance = make_instance(
        [(3, 2), (1, 4), (0, 2), (4, 1)],
        [2, 2, 1, 2],
        batch_size=4,
        shelf_life=3,
        run_cost=17,
        waste_cost=2,
        changeover_cost=5,
    )
    actual = output("run", instance)
    assert actual is not None
    assert actual == reference_plan(instance, actual["run_counts"])
    assert actual["total_produced_doses"] == (
        actual["total_runs"] * instance["batch_size"]
    )
    assert sum(row["used_doses"] for row in actual["production"]) == sum(
        row["doses"] for row in actual["allocations"]
    )


def test_c3_accepts_optimal_plan():
    """Audit a canonical two-product plan assembled independently."""
    instance = make_instance(
        [(2, 1), (3, 2), (1, 3)],
        [2, 2, 2],
        batch_size=4,
        shelf_life=2,
        run_cost=23,
        waste_cost=4,
        changeover_cost=8,
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
    """Reject a plan with a changed self-reported cost."""
    instance = make_instance(
        [(1, 2), (2, 1), (0, 2)],
        [2, 2, 1],
        batch_size=4,
        shelf_life=2,
        run_cost=20,
        waste_cost=3,
        changeover_cost=6,
    )
    expected = brute_force_plan(instance)
    tampered = copy.deepcopy(expected)
    tampered["total_cost_cents"] += 1
    actual = output("audit", instance, tampered)
    assert actual is not None
    assert actual["valid"] is False
    assert actual["minimum_cost_cents"] == expected["total_cost_cents"]


def test_c3_rejects_missing_production():
    """Reject a plan with an incomplete per-product production summary."""
    instance = make_instance(
        [(3, 0), (0, 3), (2, 2)],
        [1, 1, 2],
        batch_size=4,
        shelf_life=3,
        run_cost=11,
        waste_cost=2,
        changeover_cost=4,
    )
    expected = brute_force_plan(instance)
    incomplete = copy.deepcopy(expected)
    incomplete["production"] = expected["production"][1:]
    actual = output("audit", instance, incomplete)
    assert actual is not None
    assert actual["valid"] is False


def test_c3_rejects_nonoptimal_run_counts():
    """Reject a feasible two-product schedule that is not cheapest."""
    instance = make_instance(
        [(4, 0), (0, 4), (2, 2)],
        [2, 2, 2],
        batch_size=4,
        shelf_life=5,
        run_cost=10,
        waste_cost=1,
        changeover_cost=2,
    )
    candidate = second_best_plan(instance)
    actual = output("audit", instance, candidate)
    assert actual is not None
    assert actual["valid"] is False


def test_c3_invalid_instance_preserves_output():
    """Reject a malformed demand object without replacing an existing file."""
    instance = make_instance([(1, 1)], [1])
    instance["shifts"][0]["demand"] = {"A": 1}
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


def test_c4_storage_capacity_rejects_unavoidable_hold():
    """Reject one-shift stock that exceeds the shared cold-room limit."""
    instance = make_instance(
        [(1, 1)],
        [2],
        batch_size=4,
        shelf_life=2,
        run_cost=10,
        waste_cost=1,
        changeover_cost=3,
        storage_capacity=2,
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        instance_path = root / "instance.json"
        output_path = root / "output.json"
        instance_path.write_text(json.dumps(instance), encoding="utf-8")
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
        assert not output_path.exists()


def test_c4_storage_capacity_changes_plan():
    """Choose a staged schedule when early production would overfill storage."""
    instance = make_instance(
        [(1, 0), (3, 3)],
        [2, 2],
        batch_size=4,
        shelf_life=3,
        run_cost=10,
        waste_cost=1,
        changeover_cost=1,
        storage_capacity=4,
    )
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected
    assert expected["run_counts"][0] == {"shift": 0, "A": 1, "B": 0}


def test_c4_storage_capacity_audit():
    """Reject a supplied plan whose retained doses exceed the stated limit."""
    instance = make_instance(
        [(1, 0), (3, 3)],
        [2, 2],
        batch_size=4,
        shelf_life=3,
        run_cost=10,
        waste_cost=1,
        changeover_cost=3,
        storage_capacity=4,
    )
    tampered = {
        "instance_id": instance["instance_id"],
        "run_counts": [
            {"shift": 0, "A": 1, "B": 1},
            {"shift": 1, "A": 1, "B": 1},
        ],
        "production": [
            {
                "production_shift": 0,
                "sku": "A",
                "runs": 1,
                "produced_doses": 4,
                "used_doses": 1,
                "wasted_doses": 0,
            },
            {
                "production_shift": 0,
                "sku": "B",
                "runs": 1,
                "produced_doses": 4,
                "used_doses": 1,
                "wasted_doses": 0,
            },
            {
                "production_shift": 1,
                "sku": "A",
                "runs": 1,
                "produced_doses": 4,
                "used_doses": 3,
                "wasted_doses": 1,
            },
            {
                "production_shift": 1,
                "sku": "B",
                "runs": 1,
                "produced_doses": 4,
                "used_doses": 3,
                "wasted_doses": 1,
            },
        ],
        "allocations": [
            {"production_shift": 0, "sku": "A", "use_shift": 0, "doses": 1},
            {"production_shift": 0, "sku": "B", "use_shift": 0, "doses": 1},
            {"production_shift": 0, "sku": "A", "use_shift": 1, "doses": 3},
            {"production_shift": 0, "sku": "B", "use_shift": 1, "doses": 3},
            {"production_shift": 1, "sku": "A", "use_shift": 1, "doses": 0},
            {"production_shift": 1, "sku": "B", "use_shift": 1, "doses": 0},
        ],
        "total_runs": 4,
        "total_produced_doses": 16,
        "total_wasted_doses": 2,
        "total_changeovers": 2,
        "total_cost_cents": 48,
    }
    actual = output("audit", instance, tampered)
    assert actual is not None
    assert actual["valid"] is False


def test_e2e_example_instance():
    """Match the bundled two-product example against enumeration."""
    instance = json.loads((WORKSPACE / "example.json").read_text(encoding="utf-8"))
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected


def test_e2e_generated_seven_shift_instance():
    """Handle a generated mixed-capacity horizon with changeovers."""
    instance = generated_instance(20261023, 7)
    expected = brute_force_plan(instance)
    actual = output("run", instance)
    assert actual == expected
