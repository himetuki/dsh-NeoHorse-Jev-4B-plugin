"""Freeze, execute, resume, replay, and summarize a DeepSWE paired batch."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DSH_VERSION, PlanError, digest, evaluator_hashes, load, plan_hash, require_real_toolset, schedule, tree_digest
from .report import summarize


ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dsh_package(plan: dict[str, Any]) -> dict[str, Any]:
    return {"name": "jev-deepswe-dsh-runtime", "version": "1.0.0", "private": True,
            "dependencies": {"@deepseek-ai/dsh": DSH_VERSION, "pnpm": plan["versions"]["pnpm"]}}


def _check_dsh_lock(batch: Path, plan: dict[str, Any]) -> None:
    directory = batch / "dsh-install"
    identity = _read(directory / "identity.json")
    package = _read(directory / "package.json")
    lock = _read(directory / "package-lock.json")
    if identity is None or package != _dsh_package(plan) or lock is None:
        raise PlanError("Frozen DSH npm lock is missing or does not match the plan")
    if identity.get("package_sha256") != digest(directory / "package.json") or identity.get("lock_sha256") != digest(directory / "package-lock.json"):
        raise PlanError("Frozen DSH npm lock changed")
    if (lock.get("packages") or {}).get("", {}).get("dependencies") != package["dependencies"]:
        raise PlanError("Frozen DSH npm lock root dependencies differ")
    urls = [item.get("resolved", "") for item in lock.get("packages", {}).values() if isinstance(item, dict) and item.get("resolved")]
    if any(not url.startswith("https://registry.npmjs.org/") for url in urls):
        raise PlanError("DSH npm lock contains a non-registry package URL")


def _prepare_dsh_lock(batch: Path, plan: dict[str, Any]) -> None:
    directory = batch / "dsh-install"
    if (directory / "identity.json").exists():
        _check_dsh_lock(batch, plan)
        return
    directory.mkdir(parents=True, exist_ok=True)
    _write(directory / "package.json", _dsh_package(plan))
    user_config = directory / "npm-user.npmrc"
    global_config = directory / "npm-global.npmrc"
    for config in (user_config, global_config):
        if config.exists() and config.read_bytes():
            raise PlanError("Batch-owned npm configuration must be empty")
        config.touch(mode=0o600)
    env = {name: value for name, value in os.environ.items() if not name.lower().startswith("npm_config_")}
    env.update(npm_config_registry="https://registry.npmjs.org/",
               npm_config_userconfig=str(user_config.resolve()),
               npm_config_globalconfig=str(global_config.resolve()),
               npm_config_cache=str((directory / "npm-cache").resolve()))
    result = subprocess.run(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
                            cwd=directory, env=env, capture_output=True, text=True)
    if result.returncode:
        raise PlanError(f"Cannot freeze DSH npm transitive packages: {(result.stderr or result.stdout)[-700:]}")
    _write(directory / "identity.json", {"package_sha256": digest(directory / "package.json"),
                                           "lock_sha256": digest(directory / "package-lock.json"),
                                           "registry": "https://registry.npmjs.org/"})
    _check_dsh_lock(batch, plan)


def _image_reference(task: dict[str, Any], source: Path) -> str:
    with (source / "task.toml").open("rb") as handle:
        info = tomllib.load(handle)
    image = info["environment"]["docker_image"]
    base = image.split("@", 1)[0]
    tail = base.rsplit("/", 1)[-1]
    if ":" in tail:
        base = base[:-(len(tail) - tail.rfind(":"))]
    return f"{base}@{task['image_digest']}"


def _prepare_task(batch: Path, plan: dict[str, Any], task: dict[str, Any]) -> Path:
    source = Path(plan["paths"]["deep_swe"]) / "tasks" / task["id"]
    target = batch / "prepared-tasks" / task["id"]
    pinned = _image_reference(task, source)
    docker = subprocess.run(["docker", "pull", "--platform", task["platform"], pinned], capture_output=True, text=True)
    if docker.returncode:
        raise PlanError(f"Cannot pull pinned image for {task['id']}: {(docker.stderr or docker.stdout)[-700:]}")
    inspected = subprocess.run(["docker", "image", "inspect", pinned, "--format", "{{json .RepoDigests}}"], capture_output=True, text=True)
    if inspected.returncode or task["image_digest"] not in inspected.stdout:
        raise PlanError(f"Cannot verify pinned image digest for {task['id']}")
    platform = subprocess.run(["docker", "image", "inspect", pinned, "--format", "{{.Os}}/{{.Architecture}}"], capture_output=True, text=True)
    if platform.returncode or platform.stdout.strip() != task["platform"]:
        raise PlanError(f"Pinned image platform differs from {task['platform']} for {task['id']}")
    if target.exists():
        identity = json.loads((batch / "prepared-tasks" / f"{task['id']}.identity.json").read_text())
        if identity.get("source_sha256") != task["sha256"] or identity.get("image") != pinned or identity.get("prepared_sha256") != tree_digest(target):
            raise PlanError(f"Prepared task {task['id']} changed; use a new batch")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    definition = target / "task.toml"
    text = definition.read_text(encoding="utf-8")
    found = re.findall(r'(?m)^docker_image\s*=\s*"[^"]+"\s*$', text)
    if len(found) != 1:
        raise PlanError(f"Task {task['id']} does not have one supported docker_image row")
    definition.write_text(text.replace(found[0], f"docker_image = {json.dumps(pinned)}"), encoding="utf-8")
    verifier_dockerfile = target / "tests" / "Dockerfile"
    verifier_source = source / "tests" / "Dockerfile"
    if verifier_source.is_file():
        docker_text = verifier_dockerfile.read_text(encoding="utf-8")
        from_rows = re.findall(r"(?m)^FROM\s+\S+\s*$", docker_text)
        if len(from_rows) != 1:
            raise PlanError(f"Verifier Dockerfile for {task['id']} has unsupported FROM rows")
        with (source / "task.toml").open("rb") as handle:
            original_image = tomllib.load(handle)["environment"]["docker_image"]
        if from_rows[0].split()[1] != original_image:
            raise PlanError(f"Verifier Dockerfile for {task['id']} does not share the frozen Agent base image")
        verifier_dockerfile.write_text(docker_text.replace(from_rows[0], f"FROM {pinned}"), encoding="utf-8")
    _write(batch / "prepared-tasks" / f"{task['id']}.identity.json", {
        "source_sha256": task["sha256"], "image": pinned, "platform": task["platform"],
        "prepared_sha256": tree_digest(target),
        "only_changed_fields": ["environment.docker_image", "tests/Dockerfile FROM"],
    })
    return target


def _freeze(manifest: Path, batch: Path) -> dict[str, Any]:
    plan = load(manifest)
    frozen = batch / "manifest.json"
    if frozen.exists():
        existing = load(frozen)
        if plan_hash(existing) != plan_hash(plan):
            raise PlanError("Batch already belongs to a different frozen manifest")
        if _read(batch / "evaluator-hashes.json") != evaluator_hashes():
            raise PlanError("Evaluator code changed after this batch was frozen")
    else:
        batch.mkdir(parents=True, exist_ok=True)
        _write(frozen, plan)
        _write(batch / "schedule.json", {"manifest_sha256": plan_hash(plan), "slots": schedule(plan)})
        _write(batch / "evaluator-hashes.json", evaluator_hashes())
    _prepare_dsh_lock(batch, plan)
    return plan


def _check_frozen(batch: Path) -> dict[str, Any]:
    plan = load(batch / "manifest.json")
    saved = _read(batch / "schedule.json")
    if saved is None or saved.get("manifest_sha256") != plan_hash(plan) or saved.get("slots") != schedule(plan):
        raise PlanError("Frozen schedule differs from the manifest")
    if _read(batch / "evaluator-hashes.json") != evaluator_hashes():
        raise PlanError("Evaluator code changed after this batch was frozen")
    _check_dsh_lock(batch, plan)
    return plan


def _check_real_credentials(plan: dict[str, Any]) -> None:
    """Fail before a real trial when its isolated profile has no supplied keys."""
    if plan["phase"] == "smoke":
        return
    for name in (plan["conditions"]["main_credential_env"], plan["jev"]["credential_env"]):
        if not os.environ.get(name):
            raise PlanError(f"Required credential environment variable {name} is unavailable")


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _job_config(batch: Path, plan: dict[str, Any], slot: dict[str, Any], attempt_dir: Path,
                task_path: Path, *, replay: Path | None = None) -> dict[str, Any]:
    if replay is None:
        agent = {"import_path": "bench.deepswe.agent:DshAgent", "model_name": plan["model"]["route"],
                 "override_timeout_sec": plan["budget"]["agent_timeout_sec"] + 180,
                 "override_setup_timeout_sec": 1200,
                 "kwargs": {"manifest_path": str((batch / "manifest.json").resolve()), "arm": slot["arm"],
                            "task_id": slot["task_id"]},
                 "env": {name: "${" + name + "}" for name in
                         {plan["conditions"]["main_credential_env"], plan["jev"]["credential_env"]}}}
    else:
        agent = {"import_path": "bench.deepswe.agent:PatchReplayAgent", "model_name": "saved-patch",
                 "override_timeout_sec": 120,
                 "kwargs": {"patch_path": str(replay.resolve()), "patch_sha256": digest(replay)}, "env": {}}
    return {"job_name": slot["slot_id"] + "--" + attempt_dir.name,
            "jobs_dir": str((attempt_dir / "pier-jobs").resolve()), "n_attempts": 1,
            "n_concurrent_trials": 1, "retry": {"max_retries": 0},
            "agents": [agent], "tasks": [{"path": str(task_path.resolve())}],
            "environment": {"type": "docker", "delete": True, "force_build": False},
            "verifier": {"override_timeout_sec": plan["budget"]["verifier_timeout_sec"], "disable": False}}


def _pier_command(plan: dict[str, Any], job: Path) -> list[str]:
    return ["uv", "run", "--project", plan["paths"]["pier"], "pier", "run", "--config", str(job), "--yes"]


def _exec_job(plan: dict[str, Any], attempt_dir: Path, config: dict[str, Any]) -> int:
    job = attempt_dir / "pier-job.json"
    _write(job, config)
    command = _pier_command(plan, job)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    with (attempt_dir / "pier.stdout.txt").open("w", encoding="utf-8") as stdout, (attempt_dir / "pier.stderr.txt").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=environment, start_new_session=True)
        _write(attempt_dir / "state.json", {"status": "running", "pid": process.pid, "started_at": _stamp(),
                                             "command": command, "job_sha256": digest(job)})
        try:
            return process.wait()
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            _write(attempt_dir / "state.json", {"status": "interrupted", "pid": process.pid, "finished_at": _stamp()})
            raise


def _state_after(attempt_dir: Path, slot: dict[str, Any], plan: dict[str, Any], exit_code: int) -> str:
    from .report import _one_attempt

    row = _one_attempt(attempt_dir, slot, plan)
    infrastructure_errors = {"EnvironmentStartTimeoutError", "AgentSetupTimeoutError", "VerifierTimeoutError",
                             "VerifierOutputParseError", "RewardFileNotFoundError", "RewardFileEmptyError",
                             "DownloadVerifierDirError", "AddTestsDirError"}
    if row["scorable"]:
        status = "terminal"
    elif row["verifier_infrastructure_sentinel"] or row["pier_exception"] in infrastructure_errors:
        status = "infrastructure_failure"
    elif row["termination"] == "interrupted":
        status = "interrupted"
    elif row["termination"] in ("needs-human", "budget_exhausted"):
        status = "terminal_unscored"
    else:
        status = "unknown_unscored"
    _write(attempt_dir / "state.json", {"status": status, "finished_at": _stamp(), "pier_exit_code": exit_code,
                                         "termination": row["termination"], "scorable": row["scorable"],
                                         "trial_result": row["trial_result"]})
    return status


def _spent(batch: Path, plan: dict[str, Any]) -> tuple[float, bool]:
    if not (batch / "slots").exists():
        return 0.0, True
    report = summarize(batch)
    return report["known_estimated_cost_usd"], report["missing_cost_attempts"] == 0


def _active(pid: int | None) -> bool:
    if not isinstance(pid, int):
        return False
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _owned_containers(attempt_dir: Path) -> list[str]:
    """Find running Compose containers whose trial config belongs to this attempt."""
    jobs_root = attempt_dir / "pier-jobs"
    names = set()
    for config in jobs_root.rglob("config.json"):
        if len(config.relative_to(jobs_root).parts) != 3:
            continue
        trial = _read(config)
        name = (trial or {}).get("trial_name")
        if isinstance(name, str):
            normalized = re.sub(r"[^a-z0-9_-]", "-", name.lower())
            names.add(normalized if normalized and normalized[0].isalnum() else "0" + normalized)
    if not names:
        return []
    listing = subprocess.run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project"], capture_output=True, text=True)
    if listing.returncode:
        raise PlanError("Cannot check Docker ownership before resuming a trial")
    ids = listing.stdout.split()
    if not ids:
        return []
    inspected = subprocess.run(["docker", "inspect", *ids], capture_output=True, text=True)
    if inspected.returncode:
        raise PlanError("Cannot inspect running Docker containers before resuming")
    owned = []
    for container in json.loads(inspected.stdout):
        project = ((container.get("Config") or {}).get("Labels") or {}).get("com.docker.compose.project", "")
        if any(project == name or project.startswith(name + "__verifier__") for name in names):
            owned.append(container["Id"])
    return owned


def _has_trial_identity(attempt_dir: Path) -> bool:
    jobs_root = attempt_dir / "pier-jobs"
    return any(len(file.relative_to(jobs_root).parts) == 3 and
               isinstance((_read(file) or {}).get("trial_name"), str)
               for file in jobs_root.rglob("config.json"))


def _execute_batch(batch: Path, plan: dict[str, Any], *, resume: bool, retry_interrupted: bool = False) -> None:
    for slot in schedule(plan):
        if _read(batch / "evaluator-hashes.json") != evaluator_hashes():
            raise PlanError("Evaluator code changed during the batch; stop before another trial")
        _check_dsh_lock(batch, plan)
        slot_dir = batch / "slots" / slot["slot_id"]
        attempts = sorted(slot_dir.glob("attempt-*"))
        if attempts:
            last = _read(attempts[-1] / "state.json") or {}
            if last.get("status") not in ("terminal", "terminal_unscored") and not _has_trial_identity(attempts[-1]):
                raise PlanError(f"Slot {slot['slot_id']} lacks Pier trial identity; inspect Docker manually before any retry")
            if last.get("status") == "running":
                if _active(last.get("pid")):
                    raise PlanError(f"Slot {slot['slot_id']} still has an active Pier process")
                if containers := _owned_containers(attempts[-1]):
                    raise PlanError(f"Slot {slot['slot_id']} still owns active Docker containers: {containers}")
                last["status"] = "interrupted"
                _write(attempts[-1] / "state.json", last)
            if _owned_containers(attempts[-1]):
                raise PlanError(f"Slot {slot['slot_id']} still owns active Docker containers")
            if last.get("status") in ("terminal", "terminal_unscored"):
                continue
            if last.get("status") in ("interrupted", "infrastructure_failure"):
                allowed = plan["budget"].get("max_infrastructure_retries", 0)
                if not retry_interrupted or len(attempts) > allowed:
                    raise PlanError(f"Slot {slot['slot_id']} needs explicit, planned retry; prior attempt is preserved")
            else:
                raise PlanError(f"Slot {slot['slot_id']} has an unresolved prior attempt")
        spent, complete = _spent(batch, plan)
        if spent >= plan["budget"]["max_batch_spend_usd"]:
            raise PlanError("Known estimated spend reached the advisory ceiling; no new trial started")
        if not complete and plan["budget"]["usage_incomplete_policy"] == "halt":
            raise PlanError("Usage is incomplete; cost policy halts before another trial")
        task = next(value for value in plan["tasks"] if value["id"] == slot["task_id"])
        pinned_task = _prepare_task(batch, plan, task)
        attempt = slot_dir / f"attempt-{len(attempts) + 1:03d}"
        attempt.mkdir(parents=True)
        _write(attempt / "identity.json", {"slot": slot, "manifest_sha256": plan_hash(plan),
                                           "task_source_sha256": task["sha256"],
                                           "prepared_task_sha256": tree_digest(pinned_task)})
        config = _job_config(batch, plan, slot, attempt, pinned_task)
        code = _exec_job(plan, attempt, config)
        status = _state_after(attempt, slot, plan, code)
        if status != "terminal":
            raise PlanError(f"Pier attempt ended {status}; inspect {attempt} before resuming")


def _reverify(batch: Path, slot_id: str, attempt_number: int) -> Path:
    plan = _check_frozen(batch)
    slots = {slot["slot_id"]: slot for slot in schedule(plan)}
    if slot_id not in slots:
        raise PlanError("Unknown frozen slot")
    slot = slots[slot_id]
    source = batch / "slots" / slot_id / f"attempt-{attempt_number:03d}"
    jobs_root = source / "pier-jobs"
    results = [file for file in jobs_root.rglob("result.json") if len(file.relative_to(jobs_root).parts) == 3]
    if len(results) != 1:
        raise PlanError("Saved source attempt has no unique Pier trial")
    patch = results[0].parent / "agent" / "patch.diff"
    if not patch.is_file():
        raise PlanError("Saved patch is missing; cannot reverify")
    task = next(value for value in plan["tasks"] if value["id"] == slot["task_id"])
    pinned_task = _prepare_task(batch, plan, task)
    replay_root = batch / "reverification" / slot_id / f"attempt-{attempt_number:03d}"
    replay = replay_root / f"replay-{len(list(replay_root.glob('replay-*'))) + 1:03d}"
    replay.mkdir(parents=True)
    config = _job_config(batch, plan, slot, replay, pinned_task, replay=patch)
    code = _exec_job(plan, replay, config)
    _state_after(replay, slot, plan, code)
    return replay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m bench.deepswe.cli", description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    check = subs.add_parser("check", help="validate and display a plan without starting Pier or a model")
    check.add_argument("--manifest", type=Path, required=True)
    run = subs.add_parser("run", help="freeze and execute a batch")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--batch", type=Path, required=True)
    run.add_argument("--execute", action="store_true", help="explicitly permit real trial execution")
    resume = subs.add_parser("resume", help="continue a frozen batch without repeating terminal slots")
    resume.add_argument("--batch", type=Path, required=True)
    resume.add_argument("--execute", action="store_true")
    resume.add_argument("--retry-interrupted", action="store_true")
    replay = subs.add_parser("reverify", help="score one saved patch in a fresh verifier trial")
    replay.add_argument("--batch", type=Path, required=True)
    replay.add_argument("--slot", required=True)
    replay.add_argument("--attempt", type=int, required=True)
    replay.add_argument("--execute", action="store_true")
    report = subs.add_parser("report", help="summarize existing evidence without model calls")
    report.add_argument("--batch", type=Path, required=True)
    report.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "check":
            plan = load(args.manifest)
            value = {"manifest_sha256": plan_hash(plan), "phase": plan["phase"], "arms": plan["arms"],
                     "tasks": [task["id"] for task in plan["tasks"]], "repeats": plan["repeats"],
                     "planned_slots": len(schedule(plan)), "budget": plan["budget"],
                     "execution": "not started", "image_pulls": "pending until run"}
        elif args.action == "run":
            if not args.execute:
                raise PlanError("run requires --execute; use check for no-model validation")
            planned = load(args.manifest)
            require_real_toolset(planned)
            _check_real_credentials(planned)
            plan = _freeze(args.manifest, args.batch)
            _execute_batch(args.batch, plan, resume=False)
            value = summarize(args.batch)
        elif args.action == "resume":
            if not args.execute:
                raise PlanError("resume requires --execute")
            plan = _check_frozen(args.batch)
            require_real_toolset(plan)
            _check_real_credentials(plan)
            _execute_batch(args.batch, plan, resume=True, retry_interrupted=args.retry_interrupted)
            value = summarize(args.batch)
        elif args.action == "reverify":
            if not args.execute:
                raise PlanError("reverify requires --execute")
            value = {"reverification": str(_reverify(args.batch, args.slot, args.attempt))}
        else:
            value = summarize(args.batch)
            if args.output:
                _write(args.output, value)
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (PlanError, FileNotFoundError, ValueError) as error:
        print(f"DeepSWE evaluation: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
