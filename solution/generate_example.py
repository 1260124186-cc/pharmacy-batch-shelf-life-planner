"""Regenerate the bundled example from the documented fixed seed."""

import json
import random
from pathlib import Path


def main():
    """Write the deterministic demonstration instance beside the task package."""
    generator = random.Random(20261022)
    demands = [
        max(0, generator.randint(0, 8) + (index % 3) - 1)
        for index in range(9)
    ]
    capacities = [1 + (index % 2) for index in range(9)]
    instance = {
        "instance_id": "pharmacy-lot-demo-20261022",
        "batch_size": 5,
        "shelf_life_shifts": 3,
        "run_cost_cents": 4600,
        "waste_cost_cents": 95,
        "shifts": [
            {
                "index": index,
                "demand": demand,
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
