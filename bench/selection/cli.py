"""Freeze and run the six-case, existing-glob-selection check one slot at a time."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path
from typing import Any

from bench.deepswe.cli import _prepare_dsh_lock, _image_reference
from bench.deepswe.config import PlanError, digest, evaluator_hashes, load

from .cases import CASE_ORDER, MARKER, cases
from .profile import CONDITIONS, selection_rows


SOURCE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = ("__init__.py", "cases.py", "profile.py", "agent.py", "cli.py",
                "analyze.py", "credential_launcher.mjs", "smoke/__init__.py",
                "smoke/check.py", "smoke/mock_provider.mjs")
SCHEDULE = tuple((case, condition) for case in CASE_ORDER for condition in CONDITIONS)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _selection_plan(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("selection_suite") != {
        "schema": 1, "cases": list(CASE_ORDER), "conditions": list(CONDITIONS),
    }:
        raise PlanError("selection_suite must declare the fixed six cases and two conditions")
    plan = load(path)
    if plan["phase"] != "pilot" or plan["arms"] != ["baseline", "log_admission"] \
            or plan["repeats"] != 1 or len(plan["tasks"]) != 1 \
            or plan["tasks"][0]["id"] != "vitest-duration-sharding":
        raise PlanError("selection suite requires one fixed Vitest seed task and baseline/log_admission adapter arms")
    if plan["conditions"]["sandbox"] != "danger-full-access" \
            or plan["conditions"]["toolset"] != "dsh-headless-no-web-tools":
        raise PlanError("selection suite requires declared full-access and no-web conditions")
    if plan["budget"]["agent_timeout_sec"] != 120 or plan["budget"]["max_infrastructure_retries"] != 0:
        raise PlanError("selection suite requires a 120-second Agent and no automatic retry")
    if "node_tarball" not in plan["paths"]:
        raise PlanError("selection suite requires a pinned Node archive for the seed image")
    if plan["model"]["provider"] != "deepseek-official" or plan["model"]["id"] != "deepseek-flash" \
            or plan["model"]["route"] != "deepseek-official/deepseek-flash" \
            or plan["model"]["reasoning_effort"] != "high":
        raise PlanError("selection suite requires the declared DeepSeek Flash/high provider route")
    if plan["conditions"]["main_credential_env"] != "DEEPSEEK_API_KEY" \
            or plan["jev"]["credential_env"] != "JEV_API_KEY":
        raise PlanError("selection suite requires the documented native credential references")
    if plan["jev"]["model"] != "jev-1.13.0":
        raise PlanError("selection suite requires an exact Jev 1.13.0 model id")
    return plan


def _published_plugin_has_stage_navigation(archive_path: Path) -> None:
    """Reject an older eleven-feature archive before composing current profiles."""
    try:
        with tarfile.open(archive_path) as archive:
            names = set(archive.getnames())
            patch_file = archive.extractfile("package/packages/jev/cordis.patch.yml")
            patch = patch_file.read().decode("utf-8") if patch_file else ""
    except (tarfile.TarError, OSError, UnicodeError, KeyError) as error:
        raise PlanError("Plugin archive cannot be inspected") from error
    if "package/runtime/stage-navigation.js" not in names or "jev-stage-navigation" not in patch:
        raise PlanError("Plugin archive lacks the current stage-navigation Loader row")


def _job_config(batch: Path, plan: dict[str, Any], case: str, condition: str) -> dict[str, Any]:
    case_root = batch / "cases" / case
    return {
        "job_name": f"jev-selection-{case}-{condition}",
        "jobs_dir": str((batch / "jobs" / case / condition).resolve()),
        "n_attempts": 1, "n_concurrent_trials": 1, "retry": {"max_retries": 0},
        "agents": [{"import_path": "bench.selection.agent:SelectionSuiteAgent",
                    "model_name": plan["model"]["route"], "override_timeout_sec": 300,
                    "override_setup_timeout_sec": 1200,
                    "kwargs": {"manifest_path": str((batch / "manifest.json").resolve()),
                               "arm": CONDITIONS[condition], "task_id": plan["tasks"][0]["id"],
                               "case_id": case, "fixture_tar_sha256": digest(case_root / "fixture.tar")},
                    "env": {"DEEPSEEK_API_KEY": "${DEEPSEEK_API_KEY}", "JEV_API_KEY": "${JEV_API_KEY}"}}],
        "tasks": [{"path": str((case_root / "task").resolve())}],
        "environment": {"type": "docker", "delete": True, "force_build": False},
        "verifier": {"disable": True},
    }


def _frozen_files(batch: Path) -> list[str]:
    names = ["manifest.json", "evaluator-hashes.json", "profile-baseline.patch.json",
             "profile-file-ranking.patch.json", "dsh-install/package.json",
             "dsh-install/package-lock.json", "dsh-install/identity.json"]
    for case in CASE_ORDER:
        names.extend(f"cases/{case}/{name}" for name in (
            "task/task.toml", "task/environment/Dockerfile", "task/instruction.md",
            "fixture.tar", "fixture-expected.json", "truth.json", "job-baseline.json", "job-file-ranking.json"))
    return names


def _source_hashes() -> dict[str, str]:
    source = Path(__file__).resolve().parent
    return {name: digest(source / name) for name in SOURCE_FILES}


def _check_image(plan: dict[str, Any]) -> str:
    task = plan["tasks"][0]
    source = Path(plan["paths"]["deep_swe"]) / "tasks" / task["id"]
    image = _image_reference(task, source)
    pull = subprocess.run(["docker", "pull", "--platform", task["platform"], image], capture_output=True, text=True)
    if pull.returncode:
        raise PlanError("Cannot pull the declared seed image")
    inspected = subprocess.run(["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}"],
                               capture_output=True, text=True)
    platform = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Os}}/{{.Architecture}}"],
                              capture_output=True, text=True)
    if inspected.returncode or task["image_digest"] not in inspected.stdout \
            or platform.returncode or platform.stdout.strip() != task["platform"]:
        raise PlanError("Seed image digest or platform differs from the manifest")
    return image


def prepare(manifest: Path, batch: Path) -> None:
    if batch.exists():
        raise PlanError("Selection batch directory already exists; choose a fresh output directory")
    plan = _selection_plan(manifest)
    _published_plugin_has_stage_navigation(Path(plan["paths"]["plugin_tarball"]))
    image = _check_image(plan)
    batch.mkdir(parents=True)
    _write(batch / "manifest.json", plan)
    _write(batch / "evaluator-hashes.json", evaluator_hashes())
    _prepare_dsh_lock(batch, plan)
    for condition in CONDITIONS:
        _write(batch / f"profile-{condition}.patch.json", selection_rows(plan, condition))
    for case, definition in cases().items():
        root = batch / "cases" / case
        task = root / "task"
        (task / "environment").mkdir(parents=True)
        (task / "task.toml").write_text(
            "schema_version = \"1.3\"\n"
            f"[task]\nname = \"local/jev-selection-{case}\"\n"
            "description = \"Read-only native DSH glob selection case\"\n"
            f"[metadata]\ntask_id = \"jev-selection-{case}\"\n"
            "[agent]\nnetwork_mode = \"no-network\"\ntimeout_sec = 120.0\n"
            "[verifier]\nnetwork_mode = \"no-network\"\n"
            "[environment]\n"
            f"docker_image = \"{image}\"\n"
            "os = \"linux\"\ncpus = 2\nmemory_mb = 8192\nstorage_mb = 20480\n"
            "gpus = 0\nmcp_servers = []\n", encoding="utf-8")
        (task / "environment" / "Dockerfile").write_text(f"FROM {image}\n", encoding="utf-8")
        directory = f"src/jev-suite/{case}"
        (task / "instruction.md").write_text(
            "This is a read-only file-location task in /app. Do not create, edit, remove, or commit files. "
            f"Use the native grep tool once with pattern {MARKER} and path {directory}; "
            f"then use the native glob tool once with pattern {directory}/**/*.ts and path '.'. "
            "Do not use bash, web tools, or skill_catalog for these searches. "
            "If a complete-result recovery path is shown, read it with the native read tool before answering. "
            "Then read the source file or files relevant to the question; if no path matches, say so rather than inventing a file. "
            "The grep marker is common to every candidate and does not identify the answer. "
            + definition["question"] + "\n", encoding="utf-8")
        expected: dict[str, str] = {}
        with tarfile.open(root / "fixture.tar", "w") as archive:
            for name, content in sorted(definition["files"].items()):
                path = f"{directory}/{name}"
                data = content.encode("utf-8")
                expected[path] = hashlib.sha256(data).hexdigest()
                entry = tarfile.TarInfo(path)
                entry.size = len(data)
                entry.mode = 0o644
                entry.mtime = 0
                archive.addfile(entry, io.BytesIO(data))
        _write(root / "fixture-expected.json", expected)
        _write(root / "truth.json", {
            "targets": [f"{directory}/{name}" for name in definition["truth"]["targets"]],
            "answer_facts": definition["truth"]["answer_facts"],
            "fact_tokens": definition["truth"]["fact_tokens"],
        })
        for condition in CONDITIONS:
            _write(root / f"job-{condition}.json", _job_config(batch, plan, case, condition))
    _write(batch / "selection-lock.json", {
        "schema": 1, "schedule": [list(item) for item in SCHEDULE],
        "candidate_counts": {name: len(value["files"]) for name, value in cases().items()},
        "file_candidates": 40, "file_limit": 12, "agent_timeout_sec": 120,
        "cost_policy": "advisory", "max_suite_spend_usd": plan["budget"]["max_batch_spend_usd"],
        "no_automatic_retries": True, "verifier": "disabled",
        "source_sha256": _source_hashes(),
        "inputs_sha256": {name: digest(batch / name) for name in _frozen_files(batch)},
    })
    check(batch)


def check(batch: Path) -> None:
    lock = json.loads((batch / "selection-lock.json").read_text(encoding="utf-8"))
    if lock["source_sha256"] != _source_hashes() \
            or lock["inputs_sha256"] != {name: digest(batch / name) for name in _frozen_files(batch)} \
            or lock["schedule"] != [list(item) for item in SCHEDULE]:
        raise PlanError("Selection source, batch inputs, or schedule differ from frozen lock")
    plan = _selection_plan(batch / "manifest.json")
    if json.loads((batch / "evaluator-hashes.json").read_text(encoding="utf-8")) != evaluator_hashes():
        raise PlanError("Shared DSH/Pier evaluator code differs from frozen batch")
    _published_plugin_has_stage_navigation(Path(plan["paths"]["plugin_tarball"]))
    from bench.deepswe.cli import _check_dsh_lock
    _check_dsh_lock(batch, plan)
    baseline = json.loads((batch / "profile-baseline.patch.json").read_text(encoding="utf-8"))
    treatment = json.loads((batch / "profile-file-ranking.patch.json").read_text(encoding="utf-8"))
    if baseline != selection_rows(plan, "baseline") or treatment != selection_rows(plan, "file-ranking"):
        raise PlanError("Profile patch differs from declared selection conditions")
    normalized = json.loads(json.dumps(treatment))
    next(row for row in normalized if row.get("id") == "jev")["config"]["features"]["file-ranking"] = False
    if normalized != baseline:
        raise PlanError("Profiles differ beyond file-ranking")
    for rows in (baseline, treatment):
        if len([row for row in rows if row.get("id") == "tool-web" and row.get("disabled") is True]) != 1 \
                or len([row for row in rows if row.get("id") == "jev-selection" and row.get("disabled") is not True]) != 1 \
                or len([row for row in rows if row.get("id") == "jev-stage-navigation" and row.get("disabled") is True]) != 1:
            raise PlanError("Selection, web, or stage-navigation Loader rows differ")
    from pier.models.job.config import JobConfig
    from pier.models.task.task import Task
    for case, definition in cases().items():
        root = batch / "cases" / case
        if len(definition["files"]) != lock["candidate_counts"][case]:
            raise PlanError("Candidate count changed")
        task = Task(root / "task")
        with (root / "task" / "task.toml").open("rb") as source:
            image = tomllib.load(source)["environment"]["docker_image"]
        if (root / "task" / "environment" / "Dockerfile").read_text(encoding="utf-8") != f"FROM {image}\n":
            raise PlanError("Task Dockerfile differs from the pinned image")
        expected = json.loads((root / "fixture-expected.json").read_text(encoding="utf-8"))
        with tarfile.open(root / "fixture.tar") as archive:
            observed = {entry.name: hashlib.sha256(archive.extractfile(entry).read()).hexdigest()
                        for entry in archive.getmembers()}
        if observed != expected:
            raise PlanError("Fixture content differs from frozen hashes")
        truth = json.loads((root / "truth.json").read_text(encoding="utf-8"))
        if any(target not in expected for target in truth["targets"]):
            raise PlanError("Truth names a path outside the fixture")
        for condition in CONDITIONS:
            job = json.loads((root / f"job-{condition}.json").read_text(encoding="utf-8"))
            if job != _job_config(batch, plan, case, condition):
                raise PlanError("Pier job differs from frozen condition")
            JobConfig.model_validate(job)
    print(json.dumps({"ready": True, "cases": list(CASE_ORDER), "trials": len(SCHEDULE),
                      "candidate_counts": lock["candidate_counts"], "profile_only_difference": "file-ranking",
                      "input_lock_sha256": digest(batch / "selection-lock.json")}, sort_keys=True))


async def preflight(batch: Path) -> None:
    from pier.job import Job
    from pier.models.job.config import JobConfig
    from pier.trial.trial import Trial
    check(batch)
    results = []
    for case, condition in SCHEDULE:
        config = JobConfig.model_validate_json((batch / "cases" / case / f"job-{condition}.json").read_text(encoding="utf-8"))
        config.job_name = f"preflight-{case}-{condition}"
        config.jobs_dir = batch / "preflight" / case / condition
        config.agents[0].env = {"DEEPSEEK_API_KEY": "preflight-placeholder", "JEV_API_KEY": "preflight-placeholder"}
        job = await Job.create(config)
        try:
            trial = await Trial.create(job._remaining_trial_configs[0])
            trial._close_logger_handler()
            results.append({"case": case, "condition": condition, "trial_created": True,
                            "container_started": False, "model_called": False})
        finally:
            job._close_logger_handlers()
    _write(batch / "pier-entry-preflight.json", results)
    print(json.dumps({"preflight_trials": len(results), "all_constructed": True,
                      "container_started": False, "model_called": False}, sort_keys=True))


def run_one(batch: Path, case: str, condition: str, execute: bool) -> None:
    if not execute:
        raise PlanError("Paid execution requires --execute")
    check(batch)
    if not os.environ.get("DEEPSEEK_API_KEY") or not os.environ.get("JEV_API_KEY"):
        raise PlanError("Native launcher did not supply both credential references")
    from .analyze import gate_before
    gate_before(batch, case, condition)
    jobs = batch / "jobs" / case / condition
    if jobs.exists():
        raise PlanError("This trial already has a job; never overwrite or retry automatically")
    jobs.mkdir(parents=True)
    plan = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(SOURCE_ROOT), env.get("PYTHONPATH", "")))
    command = ["uv", "run", "--project", plan["paths"]["pier"], "pier", "run", "--config",
               str((batch / "cases" / case / f"job-{condition}.json").resolve()), "--yes"]
    outcome = subprocess.run(command, cwd=SOURCE_ROOT, env=env, capture_output=True, text=True, errors="replace")

    def redact(output: str) -> str:
        for name in ("DEEPSEEK_API_KEY", "JEV_API_KEY"):
            output = output.replace(env[name], "[REDACTED]")
        return output

    (jobs / "pier.stdout.txt").write_text(redact(outcome.stdout), encoding="utf-8")
    (jobs / "pier.stderr.txt").write_text(redact(outcome.stderr), encoding="utf-8")
    print(json.dumps({"case": case, "condition": condition, "pier_exit_code": outcome.returncode,
                      "job_dir": str(jobs.resolve())}, sort_keys=True))
    if outcome.returncode:
        raise PlanError("Pier trial failed; preserve this job and stop for inspection")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare_cmd = sub.add_parser("prepare")
    prepare_cmd.add_argument("--manifest", type=Path, required=True)
    prepare_cmd.add_argument("--batch", type=Path, required=True)
    for action in ("check", "preflight"):
        command = sub.add_parser(action)
        command.add_argument("--batch", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--batch", type=Path, required=True)
    run.add_argument("--case", choices=CASE_ORDER, required=True)
    run.add_argument("--condition", choices=tuple(CONDITIONS), required=True)
    run.add_argument("--execute", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--batch", type=Path, required=True)
    inspect.add_argument("--case", choices=CASE_ORDER, required=True)
    inspect.add_argument("--condition", choices=tuple(CONDITIONS), required=True)
    report = sub.add_parser("report")
    report.add_argument("--batch", type=Path, required=True)
    report.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            prepare(args.manifest.resolve(), args.batch.resolve())
        elif args.action == "check":
            check(args.batch.resolve())
        elif args.action == "preflight":
            asyncio.run(preflight(args.batch.resolve()))
        elif args.action == "run":
            run_one(args.batch.resolve(), args.case, args.condition, args.execute)
        elif args.action == "inspect":
            from .analyze import inspect_slot
            print(json.dumps(inspect_slot(args.batch.resolve(), args.case, args.condition),
                             ensure_ascii=False, indent=2, sort_keys=True))
        else:
            from .analyze import report_batch
            report_batch(args.batch.resolve(), (args.output or args.batch / "report.json").resolve())
        return 0
    except (PlanError, FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Selection evaluation: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
