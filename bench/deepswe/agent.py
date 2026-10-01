"""Pier Agent adapter for an isolated, published DSH headless profile."""

from __future__ import annotations

import asyncio
import json
import shlex
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pier.agents.base import BaseAgent
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.agent.network import NetworkAllowlist

from .config import DSH_VERSION, digest, evaluator_hashes, load, require_real_toolset
from .profile import write_patch


REMOTE = "/tmp/jev-deepswe"
PROFILE = "jev-eval"
GUARD = f"{REMOTE}/interaction_guard.mjs"


class DshAgent(BaseAgent):
    """Run one ordinary DSH turn; Pier still owns trial isolation and verification."""

    def __init__(self, logs_dir: Path, model_name: str | None = None, *, manifest_path: str,
                 arm: str, task_id: str, extra_env: dict[str, str] | None = None, **kwargs: Any):
        super().__init__(logs_dir, model_name=model_name, **kwargs)
        self.plan = load(Path(manifest_path))
        require_real_toolset(self.plan)
        stored_hashes = json.loads((Path(manifest_path).parent / "evaluator-hashes.json").read_text(encoding="utf-8"))
        if stored_hashes != evaluator_hashes():
            raise RuntimeError("Evaluator code differs from the frozen batch")
        install = Path(manifest_path).parent / "dsh-install"
        identity = json.loads((install / "identity.json").read_text(encoding="utf-8"))
        if digest(install / "package.json") != identity["package_sha256"] or digest(install / "package-lock.json") != identity["lock_sha256"]:
            raise RuntimeError("DSH npm installation lock differs from the frozen batch")
        self.install_files = install
        self.arm = arm
        self.task = next((task for task in self.plan["tasks"] if task["id"] == task_id), None)
        if self.task is None:
            raise ValueError(f"Task {task_id} is not in the frozen plan")
        if arm not in self.plan["arms"]:
            raise ValueError(f"Arm {arm} is not in the frozen plan")
        self.extra_env = dict(extra_env or {})
        self.workdir: str | None = None
        self.base_commit: str | None = None
        self.node_bin = ""

    @staticmethod
    def name() -> str:
        return "dsh-jev-eval"

    def version(self) -> str:
        return DSH_VERSION

    def network_allowlist(self) -> NetworkAllowlist:
        """Pier's filtered proxy permits only inference and pinned npm packages."""
        endpoints = (self.plan["model"]["endpoint"], self.plan["jev"]["endpoint"])
        domains = {"registry.npmjs.org"}
        for endpoint in endpoints:
            host = urlparse(endpoint).hostname
            if host is None:
                raise ValueError("Model endpoint has no hostname")
            domains.add(host)
        return NetworkAllowlist(domains=sorted(domains))

    async def _checked(self, environment: BaseEnvironment, command: str, *, timeout: int = 120,
                       cwd: str | None = None, env: dict[str, str] | None = None) -> str:
        result = await environment.exec(command, timeout_sec=timeout, cwd=cwd,
                                        env=environment.agent_process_env(env))
        if result.return_code != 0:
            detail = (result.stderr or result.stdout or "").strip()[-1200:]
            raise RuntimeError(f"DSH evaluation setup failed ({result.return_code}): {detail}")
        return (result.stdout or "").strip()

    def _env(self, *, credentials: bool = False) -> dict[str, str]:
        return {
            **(self.extra_env if credentials else {}),
            "DSH_HOME": f"{REMOTE}/home",
            "DSH_PERMISSION_MODE": self.plan["conditions"]["sandbox"],
            "JEV_EVAL_INTERACTIONS": "/logs/agent/interactions.jsonl",
            "JEV_EVAL_READY_MARKER": "/logs/agent/jev-service-ready.json",
            "JEV_EVAL_PROVIDER": self.plan["model"]["provider"],
            "JEV_EVAL_MODEL": self.plan["model"]["id"],
            "JEV_EVAL_CONTEXT_WINDOW": str(self.plan["conditions"]["context_window"]),
            "JEV_EVAL_DSH_PACKAGE_JSON": f"{REMOTE}/cli/node_modules/@deepseek-ai/dsh/package.json",
            "NODE_USE_ENV_PROXY": "1",
            **({"NO_PROXY": "127.0.0.1,localhost", "JEV_EVAL_MOCK_SCENARIO": self.plan["model"].get("mock_scenario", "patch"),
                "JEV_EVAL_MOCK_JEV_PORT": str(urlparse(self.plan["jev"]["endpoint"]).port or 45454),
                "JEV_EVAL_MOCK_JEV_MODE": self.plan["model"].get("mock_jev_mode", "normal"),
                "JEV_EVAL_MOCK_JEV_LOG": "/logs/agent/mock-jev.requests.jsonl",
                "JEV_EVAL_MOCK_TOOLS_LOG": "/logs/agent/mock-model-tools.json"}
               if self.plan["phase"] == "smoke" else {}),
            "PATH": f"{self.node_bin}{REMOTE}/cli/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
        }

    async def setup(self, environment: BaseEnvironment) -> None:
        if str(environment.task_os) not in ("TaskOS.LINUX", "linux"):
            raise RuntimeError("The current adapter supports Linux DeepSWE tasks only")
        await self._checked(environment, f"mkdir -p {REMOTE} /logs/agent", timeout=30)
        node_archive = self.plan["paths"].get("node_tarball")
        if node_archive:
            await environment.upload_file(node_archive, f"{REMOTE}/node.tar.xz")
            await self._checked(environment, f"mkdir -p {REMOTE}/node && tar -xJf {REMOTE}/node.tar.xz -C {REMOTE}/node --strip-components=1", timeout=120)
            self.node_bin = f"{REMOTE}/node/bin:"
        env = self._env()
        version = await self._checked(environment, "node --version", env=env, timeout=30)
        if version != "v" + self.plan["versions"]["node"]:
            raise RuntimeError(f"Node {version} differs from frozen v{self.plan['versions']['node']}")
        await self._checked(environment, "npm --version", env=env, timeout=30)
        await self._checked(environment, "timeout --help >/dev/null && command -v pgrep && command -v pkill", env=env, timeout=30)
        await self._checked(environment, f"mkdir -p {REMOTE}/cli", env=env, timeout=30)
        await environment.upload_file(self.install_files / "package.json", f"{REMOTE}/cli/package.json")
        await environment.upload_file(self.install_files / "package-lock.json", f"{REMOTE}/cli/package-lock.json")
        await self._checked(environment,
            f"npm ci --prefix {REMOTE}/cli --no-audit --no-fund",
            env=env, timeout=600)
        bootstrap_pnpm = await self._checked(environment, "pnpm --version", cwd=f"{REMOTE}/cli", env=env, timeout=30)
        if bootstrap_pnpm != self.plan["versions"]["pnpm"]:
            raise RuntimeError("DSH bootstrap pnpm version differs from plan")
        dsh = f"node {REMOTE}/cli/node_modules/@deepseek-ai/dsh/lib/bin.js"
        dsh_version = await self._checked(environment, dsh + " --version", env=env, timeout=30)
        if dsh_version != DSH_VERSION:
            raise RuntimeError("Container DSH version differs from plan")
        artifact = Path(self.plan["paths"]["plugin_tarball"])
        if digest(artifact) != self.plan["versions"]["plugin_tar_sha256"]:
            raise RuntimeError("Plugin artifact changed after plan check")
        await environment.upload_file(artifact, f"{REMOTE}/plugin.tgz")
        await environment.upload_file(Path(__file__).with_name("interaction_guard.mjs"), GUARD)
        await environment.upload_file(Path(__file__).with_name("evidence_export.mjs"), f"{REMOTE}/evidence_export.mjs")
        await environment.upload_file(Path(__file__).with_name("sandbox_precheck.mjs"), f"{REMOTE}/sandbox_precheck.mjs")
        fixture = self.plan["model"].get("fixture_module")
        if fixture:
            await environment.upload_file(fixture, f"{REMOTE}/mock-provider.mjs")
            await environment.upload_file(Path(__file__).parent / "smoke" / "mock_jev.mjs", f"{REMOTE}/mock-jev.mjs")
            await self._checked(environment,
                f"node {REMOTE}/mock-jev.mjs > /logs/agent/mock-jev.stdout.txt 2> /logs/agent/mock-jev.stderr.txt < /dev/null & "
                "echo $! > /logs/agent/mock-jev.pid; sleep 1; kill -0 $(cat /logs/agent/mock-jev.pid)",
                env=env, timeout=10)
        await self._checked(environment,
            f"{dsh} --profile {PROFILE} --from-default-profile headless --dump-default-config > /logs/agent/default-config.yml",
            env=env, timeout=60)
        await self._checked(environment, f"{dsh} plugin --profile {PROFILE} add {REMOTE}/plugin.tgz",
                            env=env, timeout=180)
        patch = self.logs_dir / "arm.patch.json"
        write_patch(patch, self.plan, self.arm, guard_path=GUARD,
                    model_module_path=f"{REMOTE}/mock-provider.mjs" if fixture else None)
        await environment.upload_file(patch, f"{REMOTE}/arm.patch.json")
        await self._checked(environment,
            f"{dsh} --profile {PROFILE} --patch {REMOTE}/arm.patch.json --dump-config > /logs/agent/profile-config.yml",
            env=env, timeout=60)
        if self.plan["phase"] == "smoke" and self.task.get("smoke_init_script"):
            await environment.upload_file(self.task["smoke_init_script"], f"{REMOTE}/smoke-init.sh")
            await self._checked(environment, f"sh {REMOTE}/smoke-init.sh", timeout=60)
            self.workdir = self.task["smoke_workdir"]
        else:
            self.workdir = await self._checked(environment, "pwd", timeout=30)
        if not self.workdir.startswith("/") or not self.workdir:
            raise RuntimeError("Pier did not provide an absolute task workdir")
        task_pnpm = await self._checked(environment, "pnpm --version", cwd=self.workdir, env=env, timeout=30)
        self.base_commit = await self._checked(environment, "git rev-parse HEAD", cwd=self.workdir, timeout=30)
        if self.plan["phase"] != "smoke":
            task_file = Path(self.plan["paths"]["deep_swe"]) / "tasks" / self.task["id"] / "task.toml"
            with task_file.open("rb") as source:
                expected_base = tomllib.load(source)["metadata"]["base_commit_hash"]
            if self.base_commit != expected_base:
                raise RuntimeError("Task image checkout does not match DeepSWE metadata.base_commit_hash")
        if await self._checked(environment, "git status --porcelain", cwd=self.workdir, timeout=30):
            raise RuntimeError("Task checkout is dirty before DSH starts")
        (self.logs_dir / "base-commit.txt").write_text(self.base_commit + "\n", encoding="utf-8")
        (self.logs_dir / "identity.json").write_text(json.dumps({
            "arm": self.arm, "dsh": DSH_VERSION, "model": self.plan["model"],
            "plugin_tar_sha256": self.plan["versions"]["plugin_tar_sha256"],
            "bootstrap_pnpm": bootstrap_pnpm, "task_pnpm": task_pnpm,
            "workdir": self.workdir, "base_commit": self.base_commit,
            "sandbox_mode": self.plan["conditions"]["sandbox"],
        }, sort_keys=True) + "\n", encoding="utf-8")
        try:
            await self._checked(environment, f"node {REMOTE}/sandbox_precheck.mjs", cwd=self.workdir,
                                env={**env, "JEV_EVAL_SANDBOX_WORKDIR": self.workdir,
                                     "JEV_EVAL_SANDBOX_MODE": self.plan["conditions"]["sandbox"],
                                     "JEV_EVAL_SANDBOX_PRECHECK_MARKER": "/logs/agent/sandbox-precheck.json"}, timeout=20)
        except RuntimeError:
            # Pier does not always export /logs/agent after setup raises.
            try:
                await environment.download_file("/logs/agent/sandbox-precheck.json", self.logs_dir / "sandbox-precheck.json")
            except Exception as _download_error:
                # The marker may not exist if module loading failed; keep the
                # original sandbox setup error as the trial's failure reason.
                pass
            raise

    async def _finish(self, environment: BaseEnvironment, context: AgentContext) -> None:
        if self.workdir is None or self.base_commit is None:
            context.metadata = {**(context.metadata or {}), "patch_status": "missing_base"}
            return
        try:
            active = await environment.exec("pgrep -f '[d]sh/lib/bin.js'", timeout_sec=10)
            if active.return_code == 0:
                await environment.exec("pkill -TERM -f '[d]sh/lib/bin.js' || true; sleep 3; pkill -KILL -f '[d]sh/lib/bin.js' || true", timeout_sec=15)
                active = await environment.exec("pgrep -f '[d]sh/lib/bin.js'", timeout_sec=10)
                if active.return_code == 0:
                    context.metadata = {**(context.metadata or {}), "patch_status": "process_active"}
                    return
        except Exception as exc:
            context.metadata = {**(context.metadata or {}), "patch_status": "quiescence_unknown", "patch_error": str(exc)[-500:]}
            return
        qbase = shlex.quote(self.base_commit)
        cmd = (
            "git add -A && "
            "(git diff --cached --quiet || git -c user.name='DSH Eval' -c user.email='eval@invalid.local' commit -m 'Collect agent work') && "
            f"git diff --binary --full-index {qbase} HEAD > /logs/agent/patch.diff"
        )
        try:
            result = await environment.exec(cmd, cwd=self.workdir, timeout_sec=90)
            status = "collected" if result.return_code == 0 else "failed"
            error = None if status == "collected" else (result.stderr or result.stdout or "")[-500:]
        except Exception as exc:
            status, error = "failed", str(exc)[-500:]
        context.metadata = {**(context.metadata or {}), "patch_status": status,
                            "patch_error": error}
        try:
            export = await environment.exec(f"node {REMOTE}/evidence_export.mjs", env=self._env(), timeout_sec=30)
            context.metadata = {**(context.metadata or {}), "evidence_export": "complete" if export.return_code == 0 else "failed",
                                "evidence_export_error": None if export.return_code == 0 else (export.stderr or export.stdout or "")[-500:]}
        except Exception as exc:
            context.metadata = {**(context.metadata or {}), "evidence_export": "failed", "evidence_export_error": str(exc)[-500:]}
        try:
            question = await environment.exec("test -s /logs/agent/interactions.jsonl", timeout_sec=10)
            if question.return_code == 0:
                context.metadata = {**(context.metadata or {}), "termination": "needs-human"}
        except Exception:
            context.metadata = {**(context.metadata or {}), "interaction_evidence": "unavailable"}

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        if self.workdir is None:
            raise RuntimeError("setup did not establish task workdir")
        context.metadata = {"arm": self.arm, "termination": "running"}
        instruction_path = self.logs_dir / "instruction.txt"
        instruction_path.write_text(instruction, encoding="utf-8")
        await environment.upload_file(instruction_path, f"{REMOTE}/instruction.txt")
        dsh = f"node {REMOTE}/cli/node_modules/@deepseek-ai/dsh/lib/bin.js"
        limit = self.plan["budget"]["agent_timeout_sec"]
        cmd = (f"timeout --signal=TERM --kill-after=10s {limit}s "
               f"{dsh} --profile {PROFILE} --patch {REMOTE}/arm.patch.json --json - "
               f"< {REMOTE}/instruction.txt > /logs/agent/dsh.stdout.jsonl 2> /logs/agent/dsh.stderr.txt")
        try:
            result = await environment.exec(cmd, cwd=self.workdir,
                env=environment.agent_process_env(self._env(credentials=True)),
                timeout_sec=limit + 30)
            context.metadata = {**(context.metadata or {}), "dsh_exit_code": result.return_code,
                                "termination": "budget_exhausted" if result.return_code in (124, 137)
                                else "normal" if result.return_code == 0 else "agent_error"}
        except asyncio.CancelledError:
            # Pier's outer timeout and an operator cancellation both cancel this
            # coroutine. Its TrialResult exception distinguishes them later.
            context.metadata = {**(context.metadata or {}), "termination": "interrupted"}
            raise
        except RuntimeError as error:
            # Pier Docker raises this exact timeout from environment.exec; returning
            # lets Pier collect the patch and run its independent verifier.
            timed_out = str(error).startswith("Command timed out after ")
            context.metadata = {**(context.metadata or {}),
                                "termination": "budget_exhausted" if timed_out else "agent_error",
                                "execution_error": str(error)[-500:]}
        except Exception as error:
            context.metadata = {**(context.metadata or {}), "termination": "agent_error",
                                "execution_error": str(error)[-500:]}
        finally:
            collection = asyncio.create_task(self._finish(environment, context))
            try:
                await asyncio.shield(collection)
            except asyncio.CancelledError:
                await collection
                raise


class PatchReplayAgent(BaseAgent):
    """Apply an already captured patch in a new Pier trial without an LLM call."""

    def __init__(self, logs_dir: Path, model_name: str | None = None, *, patch_path: str,
                 patch_sha256: str, **kwargs: Any):
        super().__init__(logs_dir, model_name=model_name, **kwargs)
        self.patch_path = Path(patch_path)
        self.patch_sha256 = patch_sha256

    @staticmethod
    def name() -> str:
        return "dsh-patch-replay"

    def version(self) -> str:
        return "1"

    async def setup(self, environment: BaseEnvironment) -> None:
        if digest(self.patch_path) != self.patch_sha256:
            raise ValueError("Saved patch changed before replay")

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        await environment.upload_file(self.patch_path, f"{REMOTE}-replay.patch")
        result = await environment.exec(f"git apply --index {REMOTE}-replay.patch && "
            "git -c user.name='DSH Eval' -c user.email='eval@invalid.local' commit -m 'Replay saved patch'", timeout_sec=60)
        if result.return_code:
            raise RuntimeError("Saved patch did not apply cleanly to verifier task base")
        context.metadata = {"replayed_patch_sha256": self.patch_sha256}
