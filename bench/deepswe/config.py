"""Validate and freeze every input that can change a paired run."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ARMS = ("baseline", "log_admission", "completion_check")
NO_WEB_TOOLSET = "dsh-headless-no-web-tools"
LEGACY_TOOLSET = "dsh-headless-default"
FEATURES = (
    "skill-selection", "file-ranking", "drift-monitoring", "completion-check", "stage-navigation",
    "goal-supervision", "instruction-guidance", "interjection-routing",
    "shared-findings", "output-admission", "test-log-admission",
    "workspace-approval",
)
OUTPUT_DEFAULTS = {
    "generalMinChars": 6000, "testMinChars": 4000, "generalBlockChars": 1200,
    "maxGeneralBlocks": 48, "maxTestCandidates": 24, "maxRequestChars": 48000,
    "maxTaskChars": 12000, "waitMs": 4000, "omitProbability": 0.8,
    "minSavedChars": 300, "minSavedRatio": 0.1, "slowTestMs": 300,
    "duplicateMinLines": 6, "duplicateMinChars": 200,
}
DSH_VERSION = "0.1.7-rc.2"
EVALUATOR_FILES = ("config.py", "profile.py", "agent.py", "interaction_guard.mjs", "evidence_export.mjs", "report.py", "cli.py",
                   "credential_launcher.mjs", "sandbox_precheck.mjs",
                   "smoke/mock_provider.mjs", "smoke/mock_jev.mjs", "smoke/init.sh")


class PlanError(ValueError):
    """A run-affecting input is missing, inconsistent, or unsupported."""


def digest(path: Path) -> str:
    """Hash a file without loading a package archive into memory."""
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def tree_digest(path: Path) -> str:
    """Hash the task definition, including verifier files but excluding Git metadata."""
    value = hashlib.sha256()
    for file in sorted(item for item in path.rglob("*") if item.is_file() and ".git" not in item.relative_to(path).parts):
        relative = file.relative_to(path).as_posix()
        value.update(relative.encode() + b"\0" + bytes.fromhex(digest(file)))
    return value.hexdigest()


def git_head(path: Path) -> str:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    if result.returncode:
        raise PlanError(f"Cannot read fixed Git commit at {path}")
    return result.stdout.strip()


def _required(data: dict[str, Any], key: str, kind: type) -> Any:
    value = data.get(key)
    if not isinstance(value, kind) or kind is str and not value.strip():
        raise PlanError(f"Missing or invalid {key}")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise PlanError(f"{name} must be a lowercase SHA-256")
    return value


def feature_settings(arm: str) -> dict[str, bool]:
    """Return the complete, exclusive switch assignment for one arm."""
    if arm not in ARMS:
        raise PlanError(f"Unsupported arm {arm!r}")
    features = {name: False for name in FEATURES}
    if arm == "log_admission":
        features["output-admission"] = features["test-log-admission"] = True
    if arm == "completion_check":
        features["completion-check"] = True
    return features


def validate_arm_settings(arm: str, settings: dict[str, Any]) -> None:
    if settings != feature_settings(arm):
        raise PlanError(f"{arm} features differ from the declared experimental condition")


def validate(raw: dict[str, Any], *, discover: bool = True) -> dict[str, Any]:
    """Reject ambiguous conditions before any chargeable trial can start."""
    if raw.get("schema") != 1:
        raise PlanError("schema must be 1")
    if raw.get("phase") not in ("smoke", "pilot", "formal"):
        raise PlanError("phase must be smoke, pilot or formal")
    _required(raw, "selection_rule", str)
    paths = _required(raw, "paths", dict)
    versions = _required(raw, "versions", dict)
    model = _required(raw, "model", dict)
    jev = _required(raw, "jev", dict)
    conditions = _required(raw, "conditions", dict)
    budget = _required(raw, "budget", dict)
    arms = _required(raw, "arms", list)
    if len(arms) < 2 or len(arms) > 3 or len(set(arms)) != len(arms) or "baseline" not in arms or any(arm not in ARMS for arm in arms):
        raise PlanError("arms must be baseline plus log_admission and/or completion_check")
    if raw["phase"] == "pilot" and arms != ["baseline", "log_admission"]:
        raise PlanError("first pilot must compare baseline with log_admission only")
    repeats = raw.get("repeats")
    if type(repeats) is not int or repeats < 1 or repeats > 20:
        raise PlanError("repeats must be an integer between 1 and 20")
    tasks = _required(raw, "tasks", list)
    if not tasks or len(tasks) > 113 or len({task.get("id") for task in tasks if isinstance(task, dict)}) != len(tasks):
        raise PlanError("tasks must be a nonempty list of unique DeepSWE IDs")
    for field in ("deep_swe", "pier", "plugin_tarball"):
        path = Path(_required(paths, field, str))
        if not path.is_absolute():
            raise PlanError(f"paths.{field} must be absolute")
        if discover and not path.exists():
            raise PlanError(f"paths.{field} does not exist: {path}")
    if versions.get("dsh") != DSH_VERSION:
        raise PlanError(f"DSH must be pinned to {DSH_VERSION}")
    if not re.fullmatch(r"[0-9a-f]{40}", _required(versions, "deep_swe_commit", str)):
        raise PlanError("deep_swe_commit must be a full Git commit")
    if not re.fullmatch(r"[0-9a-f]{40}", _required(versions, "pier_commit", str)):
        raise PlanError("pier_commit must be a full Git commit")
    _sha(versions.get("plugin_tar_sha256"), "plugin_tar_sha256")
    _required(versions, "plugin_commit", str)
    _required(versions, "node", str)
    _required(versions, "pnpm", str)
    if "node_tarball" in paths:
        if not Path(paths["node_tarball"]).is_absolute():
            raise PlanError("node_tarball must be absolute")
        _sha(versions.get("node_tar_sha256"), "node_tar_sha256")
        if discover and digest(Path(paths["node_tarball"])) != versions["node_tar_sha256"]:
            raise PlanError("Node archive checksum differs from plan")
    for field in ("provider", "id", "route", "reasoning_effort", "endpoint"):
        _required(model, field, str)
    if model["route"] != f"{model['provider']}/{model['id']}":
        raise PlanError("model.route must name the configured provider and model")
    if not model["endpoint"].startswith(("https://", "http://")):
        raise PlanError("model.endpoint must be HTTP(S)")
    if raw["phase"] != "smoke" and model["provider"] == "deepseek-official" \
            and model["endpoint"] != "https://api.deepseek.com/anthropic":
        raise PlanError("deepseek-official real runs require the official Messages endpoint")
    if "fixture_module" in model:
        if raw["phase"] != "smoke":
            raise PlanError("A local model fixture is allowed only in smoke batches")
        fixture = Path(_required(model, "fixture_module", str))
        _sha(model.get("fixture_sha256"), "model.fixture_sha256")
        if not fixture.is_absolute() or discover and digest(fixture) != model["fixture_sha256"]:
            raise PlanError("model fixture path or checksum is invalid")
        if model.get("mock_scenario", "patch") not in ("patch", "long-log"):
            raise PlanError("unsupported smoke mock_scenario")
        if model.get("mock_jev_mode", "normal") not in ("normal", "completion-omission"):
            raise PlanError("unsupported smoke mock_jev_mode")
    if type(model.get("floating_alias")) is not bool:
        raise PlanError("model.floating_alias must state whether the server model can drift")
    for field in ("endpoint", "model", "credential_env"):
        _required(jev, field, str)
    if not str(jev["endpoint"]).startswith(("https://", "http://")):
        raise PlanError("jev.endpoint must be an HTTP(S) URL")
    if raw["phase"] == "smoke":
        if "fixture_module" not in model or urlparse(jev["endpoint"]).hostname not in ("127.0.0.1", "localhost"):
            raise PlanError("smoke requires a local model fixture and loopback Jev endpoint")
    for field in ("main_credential_env", "sandbox", "toolset", "context_window", "compaction", "spill", "network"):
        if field == "context_window":
            if type(conditions.get(field)) is not int or conditions[field] < 1:
                raise PlanError("conditions.context_window must be positive")
        else:
            _required(conditions, field, str)
    for field, value in (("conditions.main_credential_env", conditions["main_credential_env"]),
                         ("jev.credential_env", jev["credential_env"])):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
            raise PlanError(f"{field} must be an environment variable name")
    if conditions["sandbox"] not in ("workspace-write", "danger-full-access"):
        raise PlanError("conditions.sandbox must be workspace-write or danger-full-access")
    if conditions["toolset"] not in (LEGACY_TOOLSET, NO_WEB_TOOLSET):
        raise PlanError("conditions.toolset is unsupported")
    expected_conditions = {
        "compaction": "dsh-0.1.7-rc.2-default",
        "spill": "maxInlineTokens:12500", "network": "inference-and-npm-allowlist",
    }
    for field, expected in expected_conditions.items():
        if conditions[field] != expected:
            raise PlanError(f"conditions.{field} must be {expected}; the adapter does not control other values")
    for field in ("agent_timeout_sec", "verifier_timeout_sec"):
        if type(budget.get(field)) is not int or budget[field] < 1:
            raise PlanError(f"budget.{field} must be a positive integer")
    if budget.get("hard_usd_cap") is not None:
        raise PlanError("a hard USD cap is unavailable for this provider path; omit it or supply a separately enforced provider limit")
    if budget.get("cost_policy") != "advisory" or type(budget.get("max_batch_spend_usd")) not in (int, float) \
            or not math.isfinite(budget["max_batch_spend_usd"]) or budget["max_batch_spend_usd"] <= 0:
        raise PlanError("an explicit advisory batch cost ceiling is required")
    if budget.get("usage_incomplete_policy") not in ("halt", "continue-with-unknown"):
        raise PlanError("budget.usage_incomplete_policy must be explicit")
    prices = _required(raw, "prices", dict)
    for owner in ("main", "jev"):
        price = _required(prices, owner, dict)
        _required(price, "source", str)
        for field in ("input_per_million", "cache_read_per_million", "cache_write_per_million", "output_per_million"):
            if type(price.get(field)) not in (int, float) or not math.isfinite(price[field]) or price[field] < 0:
                raise PlanError(f"prices.{owner}.{field} must be nonnegative")
        if raw["phase"] != "smoke" and price["input_per_million"] == price["output_per_million"] == 0:
            raise PlanError(f"prices.{owner} cannot use all-zero primary rates for a real-model batch")
    if budget.get("max_infrastructure_retries", 0) not in (0, 1, 2):
        raise PlanError("max_infrastructure_retries must be 0, 1, or 2")
    if raw.get("concurrency", 1) != 1:
        raise PlanError("only one trial at a time is supported")
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", task["id"]) is None:
            raise PlanError("each task needs a safe DeepSWE id")
        _sha(task.get("sha256"), f"{task['id']}.sha256")
        if not isinstance(task.get("image_digest"), str) or re.fullmatch(r"sha256:[0-9a-f]{64}", task["image_digest"]) is None:
            raise PlanError(f"{task['id']} needs a pinned image digest")
        if task.get("platform") not in ("linux/amd64", "linux/arm64"):
            raise PlanError(f"{task['id']} needs a fixed linux/amd64 or linux/arm64 platform")
        if raw["phase"] == "smoke" and "smoke_init_script" in task:
            init = Path(task["smoke_init_script"])
            _sha(task.get("smoke_init_sha256"), f"{task['id']}.smoke_init_sha256")
            if not init.is_absolute() or discover and digest(init) != task["smoke_init_sha256"]:
                raise PlanError(f"{task['id']} smoke init script changed")
            _required(task, "smoke_workdir", str)
    if discover:
        if git_head(Path(paths["deep_swe"])) != versions["deep_swe_commit"] or git_head(Path(paths["pier"])) != versions["pier_commit"]:
            raise PlanError("DeepSWE or Pier checkout differs from the frozen commit")
        if digest(Path(paths["plugin_tarball"])) != versions["plugin_tar_sha256"]:
            raise PlanError("plugin tarball checksum differs from plan")
        for task in tasks:
            path = Path(paths["deep_swe"]) / "tasks" / task["id"]
            if not (path / "task.toml").is_file() or tree_digest(path) != task["sha256"]:
                raise PlanError(f"task {task['id']} files differ from the frozen checksum")
            with (path / "task.toml").open("rb") as source:
                definition = tomllib.load(source)
            if definition.get("verifier", {}).get("environment_mode") != "separate":
                raise PlanError(f"task {task['id']} does not declare a separate verifier")
            if not isinstance(definition.get("verifier", {}).get("environment"), dict):
                raise PlanError(f"task {task['id']} needs an explicit verifier environment so hidden tests build separately")
            if definition.get("agent", {}).get("network_mode") != "no-network" or definition.get("verifier", {}).get("network_mode") != "no-network":
                raise PlanError(f"task {task['id']} must keep Agent and verifier no-network with Pier's inference proxy")
            if not definition.get("environment", {}).get("docker_image") or (path / "environment" / "docker-compose.yaml").exists():
                raise PlanError(f"task {task['id']} must use a prebuilt Docker image for filtered inference egress")
            base = definition.get("metadata", {}).get("base_commit_hash")
            if raw["phase"] != "smoke" and (not isinstance(base, str) or re.fullmatch(r"[0-9a-f]{40}", base) is None):
                raise PlanError(f"task {task['id']} has no fixed metadata.base_commit_hash")
            collect = definition.get("verifier", {}).get("collect", [])
            if raw["phase"] != "smoke" and (not collect or not all(base in item.get("command", "") for item in collect)):
                raise PlanError(f"task {task['id']} collect hook does not use its declared base commit")
    return raw


def require_real_toolset(plan: dict[str, Any]) -> None:
    """Preserve legacy reports while refusing search-enabled real execution."""
    if plan["phase"] != "smoke" and plan["conditions"]["toolset"] != NO_WEB_TOOLSET:
        raise PlanError("real DeepSWE execution requires dsh-headless-no-web-tools")


def load(path: Path, *, discover: bool = True) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        raw = json.load(source)
    if not isinstance(raw, dict):
        raise PlanError("manifest must be a JSON object")
    return validate(raw, discover=discover)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def plan_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(raw)).hexdigest()


def evaluator_hashes() -> dict[str, str]:
    base = Path(__file__).resolve().parent
    return {name: digest(base / name) for name in EVALUATOR_FILES}


def schedule(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Freeze balanced AB/BA order before observing any result."""
    slots = []
    for task_index, task in enumerate(raw["tasks"]):
        for repeat in range(raw["repeats"]):
            shift = (task_index + repeat) % len(raw["arms"])
            for arm in raw["arms"][shift:] + raw["arms"][:shift]:
                slots.append({"task_id": task["id"], "task_sha256": task["sha256"], "repeat": repeat, "arm": arm,
                              "slot_id": f"{task['id']}--r{repeat + 1}--{arm}"})
    return slots
