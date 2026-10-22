"""Strict JSON input and atomic JSON output helpers."""

import json
import os
import tempfile
from pathlib import Path


def _reject_constant(token):
    """Reject non-standard JSON constants such as NaN and Infinity."""
    raise ValueError(f"non-standard JSON constant: {token}")


def read_json(path):
    """Read one JSON document using the standard library parser."""
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
    )


def write_json(path, payload):
    """Write JSON through a same-directory temporary file and atomic replace."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
