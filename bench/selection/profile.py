"""Keep the installed Jev package and DSH tool catalog equal across arms."""

from __future__ import annotations

from typing import Any

from bench.deepswe.config import FEATURES
from bench.deepswe.profile import patch_rows


CONDITIONS = {"baseline": "baseline", "file-ranking": "log_admission"}
SPILL_ROOT = "/logs/agent/spills"
GUARD_REMOTE = "/tmp/jev-deepswe/interaction_guard.mjs"


def selection_rows(plan: dict[str, Any], condition: str) -> list[dict[str, Any]]:
    """Return one published DSH profile patch for a frozen selection condition."""
    rows = patch_rows(plan, CONDITIONS[condition], guard_path=GUARD_REMOTE)
    jev = next(row for row in rows if row.get("id") == "jev")
    jev["config"]["features"] = {
        name: condition == "file-ranking" and name == "file-ranking" for name in FEATURES
    }
    next(row for row in rows if row.get("id") == "jev-selection").pop("disabled")
    rows.append({"id": "spill-local", "config": {"root": SPILL_ROOT}})
    return rows
