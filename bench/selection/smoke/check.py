"""Load both selection conditions through published DSH without provider calls."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from bench.selection.cli import SOURCE_ROOT, check
from bench.selection.profile import CONDITIONS, selection_rows


def _run(argv: list[str], *, cwd: Path, env: dict[str, str], output: Path, timeout: int = 120) -> None:
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    output.write_text(result.stdout, encoding="utf-8")
    output.with_suffix(output.suffix + ".stderr").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Native DSH keyless step failed ({result.returncode}): {output.name}")


def _disabled(config: str, row_id: str) -> bool:
    match = re.search(rf"(?ms)^\s*- id: {re.escape(row_id)}\n(.*?)(?=^\s*- id: |\Z)", config)
    if match is None:
        raise RuntimeError(f"Published profile lacks {row_id}")
    return re.search(r"(?m)^\s+disabled: true\s*$", match.group(1)) is not None


def smoke(batch: Path) -> dict:
    """Use only placeholder credentials and a mock first reply in an isolated DSH home."""
    check(batch)
    plan = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    output = batch / "native-smoke"
    if output.exists():
        raise RuntimeError("Keyless native smoke already exists; keep its evidence and use a new batch")
    output.mkdir()
    home = output / "home"
    home.mkdir()
    node = shutil.which("node")
    pnpm = shutil.which("pnpm")
    dsh_bin = SOURCE_ROOT / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    package_json = dsh_bin.parent.parent / "package.json"
    if not node or not pnpm or not dsh_bin.is_file() or not package_json.is_file():
        raise RuntimeError("Install the pinned root dependencies before the native smoke")
    env = {
        "HOME": str(home), "DSH_HOME": str(home),
        "PATH": os.pathsep.join(dict.fromkeys([str(Path(pnpm).parent), str(Path(node).parent), "/usr/local/bin", "/usr/bin", "/bin"])),
        "DSH_PERMISSION_MODE": "danger-full-access",
        "JEV_API_KEY": "keyless-placeholder", "DEEPSEEK_API_KEY": "keyless-placeholder",
        "DSH_PKG_JSON": str(package_json),
    }
    launcher = [node, str(dsh_bin)]
    profile = "selection-keyless"
    _run([*launcher, "--profile", profile, "--from-default-profile", "headless", "--dump-default-config"],
         cwd=output, env=env, output=output / "default-config.yml")
    _run([*launcher, "plugin", "--profile", profile, "add", plan["paths"]["plugin_tarball"]],
         cwd=output, env=env, output=output / "plugin-add.txt", timeout=180)
    for condition in CONDITIONS:
        rows = [row for row in selection_rows(plan, condition)
                if row.get("id") != "llm-deepseek" and not
                (row.get("insert") and row["insert"][0].get("id") == "eval-interaction-guard")]
        next(row for row in rows if row.get("id") == "agent-default-model")["config"] = {
            "provider": "eval-mock", "model": "eval-mock", "reasoningEffort": "high"}
        next(row for row in rows if row.get("id") == "jev")["config"]["baseUrl"] = "http://127.0.0.1:9/v1/systemone"
        next(row for row in rows if row.get("id") == "session-persistence-jsonl")["config"]["root"] = str(output / "sessions" / condition)
        next(row for row in rows if row.get("id") == "spill-local")["config"]["root"] = str(output / "spills" / condition)
        rows.append({"insert": [{"id": "eval-mock-model", "name": str(Path(__file__).with_name("mock_provider.mjs"))}]})
        patch = output / f"{condition}.patch.json"
        patch.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        local_env = {**env, "TOOLS_LOG": str(output / f"{condition}-tools.json")}
        config_file = output / f"{condition}-config.yml"
        _run([*launcher, "--profile", profile, "--patch", str(patch), "--dump-config"],
             cwd=output, env=local_env, output=config_file)
        config = config_file.read_text(encoding="utf-8")
        if not _disabled(config, "jev-stage-navigation") or not _disabled(config, "tool-web") \
                or _disabled(config, "jev-selection"):
            raise RuntimeError("Native Loader rows differ from the declared condition")
        _run([*launcher, "--profile", profile, "--patch", str(patch), "Return a short answer without tools"],
             cwd=output, env=local_env, output=output / f"{condition}-answer.txt")
    a = json.loads((output / "baseline-tools.json").read_text(encoding="utf-8"))
    b = json.loads((output / "file-ranking-tools.json").read_text(encoding="utf-8"))
    if a != b or "skill_catalog" not in a["names"] or any(name in a["names"] for name in ("web_search", "web_fetch")):
        raise RuntimeError("Native model-visible tool catalogs differ across conditions or expose web tools")
    result = {"conditions": list(CONDITIONS), "tool_count": a["count"],
              "schema_sha256": a["schema_sha256"], "same_model_visible_tools": True,
              "web_tools": False, "stage_loader_disabled": True,
              "model": "local mock first reply", "provider_calls": 0}
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args()
    smoke(args.batch.resolve())
