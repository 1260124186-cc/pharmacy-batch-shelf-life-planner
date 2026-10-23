"""Regenerate the bundled example from the documented fixed seed."""

import json
import random
from pathlib import Path


def main():
    """Write the deterministic demonstration instance beside the task package."""
    generator = random.Random(20261023)
    demands = [(4, 4)]
    demands.extend(
        (generator.randint(0, 4), generator.randint(0, 4) + (index % 2))
        for index in range(1, 7)
    )
    capacities = [2, 2, 2, 1, 2, 2, 2]
    instance = {
        "instance_id": "pharmacy-two-product-demo-20261023",
        "batch_size": 4,
        "shelf_life_shifts": 3,
        "run_cost_cents": 3800,
        "waste_cost_cents": 70,
        "changeover_cost_cents": 900,
        "storage_capacity_doses": 20,
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
    destination = (
        Path(__file__).resolve().parents[1]
        / "environment"
        / "workspace"
        / "example.json"
    )
    destination.write_text(
        json.dumps(instance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
