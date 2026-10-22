"""Command-line entry point for planning and auditing pharmacy batches."""

import sys
from pathlib import Path

from .audit import audit_plan
from .io import read_json, write_json
from .model import PlanningError
from .planner import plan_instance


USAGE = "usage: python -m pharmacy_lots {plan|audit|run} ..."


def _dispatch(arguments):
    """Execute one command and return the payload destined for JSON output."""
    stage = arguments[0]
    if stage in {"plan", "run"} and len(arguments) == 3:
        instance = read_json(Path(arguments[1]))
        return Path(arguments[2]), plan_instance(instance)
    if stage == "audit" and len(arguments) == 4:
        instance = read_json(Path(arguments[1]))
        plan = read_json(Path(arguments[2]))
        return Path(arguments[3]), audit_plan(instance, plan)
    raise PlanningError(USAGE)


def main():
    """Run the selected command, leaving existing outputs untouched on failure."""
    arguments = sys.argv[1:]
    if not arguments:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        output, payload = _dispatch(arguments)
        write_json(output, payload)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        NotImplementedError,
    ) as exc:
        print(f"planning failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
