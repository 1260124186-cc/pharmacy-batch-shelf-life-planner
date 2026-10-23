"""Run baseline, partial-fix, and bypass specimens against the real test entry point."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


TASK = Path(__file__).resolve().parents[1]
IMAGE = "harbor-quality:pharmacy-batch-shelf-life-planner"
GROUPS = ("c1", "c2", "c3", "c4", "c5", "e2e")


def run_command(arguments):
    """Run one command without raising and keep its output for evidence."""
    return subprocess.run(
        arguments,
        text=True,
        capture_output=True,
        check=False,
    )


def copy_solution(source, destination):
    """Copy one reference or partial module into a specimen workspace."""
    shutil.copy2(TASK / "solution" / source, destination)


def override_planner(work, source):
    """Replace the planner module with a candidate implementation."""
    (work / "pharmacy_lots" / "planner.py").write_text(source, encoding="utf-8")


def specimen(root, label, files, override=None):
    """Execute one candidate workspace through the actual shell verifier."""
    work = root / label / "workspace"
    shutil.copytree(TASK / "environment" / "workspace", work)
    for entry in files:
        if isinstance(entry, tuple):
            source, destination = entry
        else:
            source = destination = entry
        copy_solution(source, work / "pharmacy_lots" / destination)
    if override is not None:
        override(work)

    logs = root / label / "logs" / "verifier"
    logs.mkdir(parents=True)
    logs.parent.chmod(0o777)
    logs.chmod(0o777)
    command = [
        "docker",
        "run",
        "--rm",
        "--user",
        "10001:10001",
        "--network",
        "host",
        "-v",
        f"{work}:/workspace:ro",
        "-v",
        f"{TASK / 'tests'}:/tests:ro",
        "-v",
        f"{logs.parent}:/logs",
        IMAGE,
        "bash",
        "/tests/test.sh",
    ]
    outcome = run_command(command)
    reward_path = logs / "reward.txt"
    reward = (
        float(reward_path.read_text(encoding="utf-8").strip())
        if reward_path.exists()
        else None
    )
    group_logs = {}
    for group in GROUPS:
        group_log = logs / f"{group}.log"
        group_logs[group] = (
            group_log.read_text(encoding="utf-8")
            if group_log.exists()
            else "missing"
        )
    evidence = TASK / "solution" / "evidence" / f"{label}.log"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        "Command: "
        + " ".join(command)
        + f"\nExit: {outcome.returncode}\nReward: {reward}\n"
        + "stdout:\n"
        + outcome.stdout
        + "\nstderr:\n"
        + outcome.stderr
        + "".join(f"\n[{group}]\n{log}" for group, log in group_logs.items()),
        encoding="utf-8",
    )
    if reward is None:
        raise RuntimeError(f"{label}: no reward file; inspect {evidence}")
    print(f"{label}: {reward:.3f}")
    return {
        "reward": reward,
        "evidence": str(evidence.relative_to(TASK)),
    }


def empty_modules(work):
    """Return empty planner and audit payloads for a bypass specimen."""
    override_planner(work, "def plan_instance(instance):\n    return {}\n")
    (work / "pharmacy_lots" / "audit.py").write_text(
        "def audit_plan(instance, plan):\n    return {}\n",
        encoding="utf-8",
    )


def fixed_zero_plan(work):
    """Return a plausible-looking but input-independent zero plan."""
    override_planner(
        work,
        "def plan_instance(instance):\n"
        "    shifts = instance.get('shifts', [])\n"
        "    return {\n"
        "        'instance_id': instance.get('instance_id'),\n"
        "        'run_counts': [0] * len(shifts),\n"
        "        'production': [],\n"
        "        'allocations': [],\n"
        "        'total_runs': 0,\n"
        "        'total_produced_doses': 0,\n"
        "        'total_wasted_doses': 0,\n"
        "        'total_cost_cents': 0,\n"
        "    }\n",
    )


def drop_audit(work):
    """Remove the audit module to exercise the import-failure path."""
    (work / "pharmacy_lots" / "audit.py").unlink()


def drop_storage_checks(work):
    """Ignore storage capacity for the C4 partial experiment."""
    module_dir = work / "pharmacy_lots"
    optimizer = module_dir / "optimizer.py"
    expander = module_dir / "expander.py"
    optimizer.write_text(
        optimizer.read_text(encoding="utf-8").replace(
            '    storage_capacity = data["storage_capacity_doses"]\n',
            "    storage_capacity = 10**18\n",
        ),
        encoding="utf-8",
    )
    expander.write_text(
        expander.read_text(encoding="utf-8").replace(
            '    storage_capacity = data["storage_capacity_doses"]\n',
            "    storage_capacity = 10**18\n",
        ),
        encoding="utf-8",
    )


def drop_use_limit(work):
    """Remove the second-use remainder rule from the expander."""
    expander = work / "pharmacy_lots" / "expander.py"
    expander.write_text(
        expander.read_text(encoding="utf-8").replace(
            "                    if bucket[\"uses\"] == 0:\n"
            "                        if bucket[\"doses\"]:\n"
            "                            bucket[\"uses\"] = 1\n"
            "                    elif bucket[\"doses\"]:\n"
            "                        key = (sku, bucket[\"production_shift\"])\n"
            "                        wasted[key] += bucket[\"doses\"]\n"
            "                        bucket[\"doses\"] = 0\n",
            "",
        ),
        encoding="utf-8",
    )


def main():
    """Build the image, run all specimens, and write the gate matrix."""
    build = run_command(
        ["docker", "build", "-q", "-t", IMAGE, str(TASK / "environment")]
    )
    if build.returncode:
        raise RuntimeError(build.stderr)

    with tempfile.TemporaryDirectory(prefix="pharmacy-quality-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        baseline = specimen(root, "baseline", [])
        oracle = specimen(
            root,
            "oracle",
            ["optimizer.py", "expander.py", "planner.py", "audit.py"],
        )
        partials = [
            {
                "challenge_id": "C1",
                **specimen(
                    root,
                    "partial-c1",
                    ["optimizer.py", "expander.py", "planner.py"],
                ),
            },
            {
                "challenge_id": "C2",
                **specimen(
                    root,
                    "partial-c2",
                    [("expander.py", "expander.py"), ("partial_c2_planner.py", "planner.py")],
                ),
            },
            {
                "challenge_id": "C3",
                **specimen(
                    root,
                    "partial-c3",
                    ["optimizer.py", "expander.py", "audit.py"],
                ),
            },
            {
                "challenge_id": "C4",
                **specimen(
                    root,
                    "partial-c4",
                    ["optimizer.py", "expander.py", "planner.py", "audit.py"],
                    drop_storage_checks,
                ),
            },
            {
                "challenge_id": "C5",
                **specimen(
                    root,
                    "partial-c5",
                    ["optimizer.py", "expander.py", "planner.py", "audit.py"],
                    drop_use_limit,
                ),
            },
        ]
        bypasses = [
            {
                "id": "B1",
                "description": "各命令返回空对象",
                **specimen(root, "bypass-empty", [], empty_modules),
            },
            {
                "id": "B2",
                "description": "固定返回全零计划",
                **specimen(root, "bypass-zero", [], fixed_zero_plan),
            },
            {
                "id": "B3",
                "description": "删除审计模块",
                **specimen(
                    root,
                    "bypass-delete",
                    ["optimizer.py", "expander.py", "planner.py"],
                    drop_audit,
                ),
            },
        ]

    report = {
        "baseline": baseline,
        "oracle": oracle,
        "partials": partials,
        "bypasses": bypasses,
    }
    (TASK / "solution" / "quality-gate-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if baseline["reward"] != 0 or oracle["reward"] != 1:
        raise RuntimeError("baseline/oracle gate failed")
    if any(not 0 < entry["reward"] < 1 for entry in partials):
        raise RuntimeError("partial gate failed")
    if any(entry["reward"] == 1 for entry in bypasses):
        raise RuntimeError("bypass gate failed")


if __name__ == "__main__":
    main()
