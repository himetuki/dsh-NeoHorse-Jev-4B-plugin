"""Pier Agent for one frozen synthetic glob-selection case."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from bench.deepswe.agent import DshAgent, PROFILE, REMOTE
from bench.deepswe.config import digest

from .cases import CASE_ORDER, cases
from .profile import SPILL_ROOT


class SelectionSuiteAgent(DshAgent):
    """Reuse DSH setup and evidence export, then apply one selection-only profile."""

    def __init__(self, *args, case_id: str, fixture_tar_sha256: str, manifest_path: str, **kwargs):
        super().__init__(*args, manifest_path=manifest_path, **kwargs)
        if case_id not in CASE_ORDER:
            raise ValueError("Unknown fixed selection case")
        self.case_id = case_id
        self.fixture_tar_sha256 = fixture_tar_sha256
        self.batch = Path(manifest_path).resolve().parent

    async def setup(self, environment):
        await super().setup(environment)
        condition = "baseline" if self.arm == "baseline" else "file-ranking"
        patch = self.batch / f"profile-{condition}.patch.json"
        lock = json.loads((self.batch / "selection-lock.json").read_text(encoding="utf-8"))
        root = self.batch / "cases" / self.case_id
        fixture = root / "fixture.tar"
        if digest(patch) != lock["inputs_sha256"][patch.relative_to(self.batch).as_posix()] \
                or digest(fixture) != self.fixture_tar_sha256:
            raise RuntimeError("Frozen selection profile or fixture changed")
        shutil.copyfile(patch, self.logs_dir / "arm.patch.json")
        await environment.upload_file(patch, f"{REMOTE}/arm.patch.json")
        dsh = f"node {REMOTE}/cli/node_modules/@deepseek-ai/dsh/lib/bin.js"
        await self._checked(environment,
                            f"{dsh} --profile {PROFILE} --patch {REMOTE}/arm.patch.json --dump-config > /logs/agent/profile-config.yml",
                            env=self._env(), timeout=60)
        await environment.upload_file(fixture, f"{REMOTE}/fixture.tar")
        directory = f"{self.workdir}/src/jev-suite/{self.case_id}"
        expected_count = len(cases()[self.case_id]["files"])
        await self._checked(environment,
                            f"mkdir -p {directory} && tar -xf {REMOTE}/fixture.tar -C {self.workdir} && "
                            f"test $(find {directory} -type f | wc -l) -eq {expected_count}",
                            env=self._env(), timeout=30)
        (self.logs_dir / "selection-condition.json").write_text(json.dumps({
            "case": self.case_id, "condition": condition, "internal_pier_arm": self.arm,
            "patch_sha256": digest(patch), "fixture_tar_sha256": self.fixture_tar_sha256,
            "spill_root": SPILL_ROOT, "candidate_count": expected_count,
        }, sort_keys=True) + "\n", encoding="utf-8")

    async def _finish(self, environment, context):
        root = self.batch / "cases" / self.case_id
        expected = json.loads((root / "fixture-expected.json").read_text(encoding="utf-8"))
        directory = f"{self.workdir}/src/jev-suite/{self.case_id}"
        try:
            observed = await environment.exec(
                f"find {directory} -type f -print0 | sort -z | xargs -0 -r sha256sum",
                cwd=self.workdir, timeout_sec=20)
            files = {}
            if observed.return_code == 0:
                for line in (observed.stdout or "").splitlines():
                    checksum, path = line.split("  ", 1)
                    files[str(Path(path).relative_to(self.workdir))] = checksum
            status = "unchanged" if observed.return_code == 0 and files == expected else "changed"
            detail = {"status": status, "expected_count": len(expected), "observed_count": len(files),
                      "different_paths": sorted({*files, *expected} -
                                                {name for name in expected if files.get(name) == expected[name]})}
        except Exception:
            status = "unknown"
            detail = {"status": status, "expected_count": len(expected)}
        (self.logs_dir / "fixture-integrity.json").write_text(
            json.dumps(detail, sort_keys=True) + "\n", encoding="utf-8")
        context.metadata = {**(context.metadata or {}), "fixture_integrity": status}
        await super()._finish(environment, context)
