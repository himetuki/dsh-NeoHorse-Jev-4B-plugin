"""Agent termination and patch collection remain separate from verifier scoring."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pier.environments.base import ExecResult
from pier.models.agent.context import AgentContext

from bench.deepswe.agent import REMOTE, DshAgent, PatchReplayAgent
from bench.deepswe.cli import _dsh_package, _write
from bench.deepswe.config import digest, evaluator_hashes
from bench.deepswe.tests.test_config_profile import plan


class FakeEnvironment:
    def __init__(self, *, dsh_exit: int = 0, dsh_error: Exception | None = None,
                 human_request: bool = False, process_stays_active: bool = False):
        self.dsh_exit = dsh_exit
        self.dsh_error = dsh_error
        self.human_request = human_request
        self.process_stays_active = process_stays_active
        self.commands: list[str] = []
        self.uploads: list[tuple[Path, str]] = []
        self.downloads: list[tuple[str, Path]] = []

    def agent_process_env(self, values: dict[str, str]) -> dict[str, str]:
        return values

    async def upload_file(self, source: Path, target: str) -> None:
        self.uploads.append((Path(source), target))

    async def download_file(self, source: str, target: Path) -> None:
        self.downloads.append((source, Path(target)))
        Path(target).write_text('{"mode":"workspace-write","status":"failed","error_code":"SANDBOX_UNAVAILABLE"}\n')

    async def exec(self, command: str, **_kwargs) -> ExecResult:
        self.commands.append(command)
        if command.startswith("timeout --signal=TERM"):
            if self.dsh_error is not None:
                raise self.dsh_error
            return ExecResult(return_code=self.dsh_exit)
        if command.startswith("pgrep -f"):
            return ExecResult(return_code=0 if self.process_stays_active else 1)
        if command.startswith("test -s /logs/agent/interactions.jsonl"):
            return ExecResult(return_code=0 if self.human_request else 1)
        return ExecResult(return_code=0)


class AgentLifecycleAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="jev-eval-agent-test-")
        self.addCleanup(self.temp.cleanup)
        self.logs = Path(self.temp.name)
        _write(self.logs / "evaluator-hashes.json", evaluator_hashes())
        install = self.logs / "dsh-install"
        package = _dsh_package(plan())
        _write(install / "package.json", package)
        _write(install / "package-lock.json", {"packages": {"": {"dependencies": package["dependencies"]}}})
        _write(install / "identity.json", {
            "package_sha256": digest(install / "package.json"),
            "lock_sha256": digest(install / "package-lock.json"),
        })

    def make_agent(self) -> DshAgent:
        with patch("bench.deepswe.agent.load", return_value=plan()):
            agent = DshAgent(self.logs, manifest_path=str(self.logs / "manifest.json"),
                             arm="baseline", task_id="task-a")
        agent.workdir = "/task"
        agent.base_commit = "a" * 40
        return agent

    def test_setup_checks_pinned_bootstrap_pnpm_in_its_own_directory(self) -> None:
        class SetupEnvironment(FakeEnvironment):
            task_os = "linux"

            def __init__(self):
                super().__init__()
                self.invocations: list[tuple[str, str | None]] = []
                self.precheck_modes: list[str | None] = []

            async def exec(self, command: str, **kwargs) -> ExecResult:
                self.invocations.append((command, kwargs.get("cwd")))
                if command == f"node {REMOTE}/sandbox_precheck.mjs":
                    self.precheck_modes.append((kwargs.get("env") or {}).get("JEV_EVAL_SANDBOX_MODE"))
                if command == "node --version":
                    output = "v22.19.0"
                elif command == "pnpm --version":
                    output = "11.7.0" if kwargs.get("cwd") == f"{REMOTE}/cli" else "10.31.0"
                elif command.endswith(" --version") and "@deepseek-ai/dsh" in command:
                    output = "0.1.7-rc.2"
                elif command == "pwd":
                    output = "/app"
                elif command == "git rev-parse HEAD":
                    output = "a" * 40
                else:
                    output = ""
                return ExecResult(return_code=0, stdout=output)

        agent = self.make_agent()
        package = self.logs / "plugin.tgz"
        package.write_bytes(b"fixture plugin archive")
        agent.plan["paths"]["plugin_tarball"] = str(package)
        agent.plan["versions"]["plugin_tar_sha256"] = digest(package)
        agent.plan["phase"] = "smoke"
        environment = SetupEnvironment()
        asyncio.run(agent.setup(environment))
        self.assertIn(("pnpm --version", f"{REMOTE}/cli"), environment.invocations)
        self.assertIn(("pnpm --version", "/app"), environment.invocations)
        self.assertIn((f"node {REMOTE}/sandbox_precheck.mjs", "/app"), environment.invocations)
        self.assertEqual(environment.precheck_modes, ["workspace-write"])
        identity = json.loads((self.logs / "identity.json").read_text())
        self.assertEqual((identity["bootstrap_pnpm"], identity["task_pnpm"]), ("11.7.0", "10.31.0"))

        full_access = self.make_agent()
        full_access.plan["paths"]["plugin_tarball"] = str(package)
        full_access.plan["versions"]["plugin_tar_sha256"] = digest(package)
        full_access.plan["phase"] = "smoke"
        full_access.plan["conditions"]["sandbox"] = "danger-full-access"
        full_environment = SetupEnvironment()
        asyncio.run(full_access.setup(full_environment))
        self.assertEqual(full_access._env()["DSH_PERMISSION_MODE"], "danger-full-access")
        self.assertEqual(full_environment.precheck_modes, ["danger-full-access"])
        self.assertEqual(json.loads((self.logs / "identity.json").read_text())["sandbox_mode"], "danger-full-access")

        class UnavailableSandbox(SetupEnvironment):
            async def exec(self, command: str, **kwargs) -> ExecResult:
                if command == f"node {REMOTE}/sandbox_precheck.mjs":
                    self.invocations.append((command, kwargs.get("cwd")))
                    return ExecResult(return_code=2, stderr="DSH workspace-write sandbox precheck failed: SANDBOX_UNAVAILABLE")
                return await super().exec(command, **kwargs)

        rejected = self.make_agent()
        rejected.plan["paths"]["plugin_tarball"] = str(package)
        rejected.plan["versions"]["plugin_tar_sha256"] = digest(package)
        rejected.plan["phase"] = "smoke"
        denied_environment = UnavailableSandbox()
        with self.assertRaisesRegex(RuntimeError, "SANDBOX_UNAVAILABLE"):
            asyncio.run(rejected.setup(denied_environment))
        self.assertEqual((self.logs / "base-commit.txt").read_text(), "a" * 40 + "\n")
        self.assertEqual(json.loads((self.logs / "identity.json").read_text())["workdir"], "/app")
        self.assertEqual(denied_environment.downloads, [
            ("/logs/agent/sandbox-precheck.json", self.logs / "sandbox-precheck.json")])
        self.assertEqual(json.loads((self.logs / "sandbox-precheck.json").read_text())["error_code"], "SANDBOX_UNAVAILABLE")
        self.assertFalse(any(" --json - " in command for command, _cwd in denied_environment.invocations))

    def test_normal_exit_collects_current_tree_relative_to_fixed_base(self) -> None:
        agent = self.make_agent()
        env = FakeEnvironment()
        context = AgentContext()
        asyncio.run(agent.run("Implement task", env, context))
        self.assertEqual(context.metadata["termination"], "normal")
        self.assertEqual(context.metadata["patch_status"], "collected")
        self.assertTrue(any("git add -A" in command and f"git diff --binary --full-index {'a' * 40} HEAD" in command
                            for command in env.commands))
        self.assertEqual(env.uploads[0][1], "/tmp/jev-deepswe/instruction.txt")
        self.assertEqual(env.uploads[0][0].read_text(), "Implement task")

    def test_timeout_keeps_termination_and_still_collects_patch(self) -> None:
        agent = self.make_agent()
        env = FakeEnvironment(dsh_exit=124)
        context = AgentContext()
        asyncio.run(agent.run("Implement task", env, context))
        self.assertEqual(context.metadata["termination"], "budget_exhausted")
        self.assertEqual(context.metadata["patch_status"], "collected")
        self.assertEqual(context.metadata["dsh_exit_code"], 124)

    def test_docker_exec_timeout_is_not_reported_as_running_or_normal(self) -> None:
        agent = self.make_agent()
        env = FakeEnvironment(dsh_error=RuntimeError("Command timed out after 60 seconds"))
        context = AgentContext()
        asyncio.run(agent.run("Implement task", env, context))
        self.assertEqual(context.metadata["termination"], "budget_exhausted")
        self.assertEqual(context.metadata["patch_status"], "collected")

    def test_actual_human_request_overrides_exit_status_without_answering(self) -> None:
        agent = self.make_agent()
        env = FakeEnvironment(human_request=True)
        context = AgentContext()
        asyncio.run(agent.run("Implement task", env, context))
        self.assertEqual(context.metadata["termination"], "needs-human")
        self.assertEqual(context.metadata["patch_status"], "collected")
        self.assertFalse(any("Retry" in command or "Cancel" in command for command in env.commands))

    def test_active_dsh_process_prevents_racy_patch_collection(self) -> None:
        agent = self.make_agent()
        env = FakeEnvironment(dsh_exit=124, process_stays_active=True)
        context = AgentContext()
        asyncio.run(agent.run("Implement task", env, context))
        self.assertEqual(context.metadata["termination"], "budget_exhausted")
        self.assertEqual(context.metadata["patch_status"], "process_active")
        self.assertTrue(any("pkill -TERM" in command for command in env.commands))
        self.assertFalse(any("git add -A" in command for command in env.commands))

    def test_replay_checks_saved_bytes_before_upload(self) -> None:
        patch_file = self.logs / "saved.patch"
        patch_file.write_text("fixed patch\n")
        agent = PatchReplayAgent(self.logs, patch_path=str(patch_file), patch_sha256=digest(patch_file))
        env = FakeEnvironment()
        asyncio.run(agent.setup(env))
        context = AgentContext()
        asyncio.run(agent.run("ignored original instruction", env, context))
        self.assertEqual(context.metadata["replayed_patch_sha256"], digest(patch_file))
        self.assertEqual(env.uploads[0][1], "/tmp/jev-deepswe-replay.patch")
        self.assertTrue(any("git apply --index" in command for command in env.commands))
        patch_file.write_text("changed patch\n")
        with self.assertRaises(ValueError):
            asyncio.run(agent.setup(env))


if __name__ == "__main__":
    unittest.main()
