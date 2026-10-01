"""The batch runner must preserve frozen slots and use Pier's declared API."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pier.models.job.config import JobConfig

from bench.deepswe.cli import _check_real_credentials, _dsh_package, _execute_batch, _job_config, _prepare_dsh_lock, _reverify, _write, main
from bench.deepswe.config import PlanError, digest, evaluator_hashes, schedule
from bench.deepswe.tests.test_config_profile import plan


class CliAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="jev-eval-cli-test-")
        self.addCleanup(self.temp.cleanup)
        self.batch = Path(self.temp.name) / "batch"
        self.batch.mkdir()
        self.raw = plan()
        _write(self.batch / "evaluator-hashes.json", evaluator_hashes())
        install = self.batch / "dsh-install"
        package = _dsh_package(self.raw)
        _write(install / "package.json", package)
        _write(install / "package-lock.json", {"packages": {"": {"dependencies": package["dependencies"]}}})
        _write(install / "identity.json", {
            "package_sha256": digest(install / "package.json"),
            "lock_sha256": digest(install / "package-lock.json"),
        })

    def state(self, slot: dict, status: str, *, attempt: int = 1, pid: int = 12345,
              trial_identity: bool = True) -> Path:
        path = self.batch / "slots" / slot["slot_id"] / f"attempt-{attempt:03d}"
        _write(path / "state.json", {"status": status, "pid": pid})
        if trial_identity:
            _write(path / "pier-jobs" / "job" / "trial" / "config.json",
                   {"trial_name": "jev-eval-fixture-trial"})
        return path

    def test_real_trial_requires_explicit_keys_without_reading_a_user_profile(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(PlanError, "FIXTURE_MAIN_KEY"):
                _check_real_credentials(self.raw)
        with patch.dict("os.environ", {"FIXTURE_MAIN_KEY": "provided", "FIXTURE_JEV_KEY": "provided"}, clear=True):
            _check_real_credentials(self.raw)
        self.raw["phase"] = "smoke"
        with patch.dict("os.environ", {}, clear=True):
            _check_real_credentials(self.raw)

    def test_npm_lock_uses_distinct_empty_batch_configs(self) -> None:
        second_batch = Path(self.temp.name) / "new-batch"

        def fake_npm(_args, *, cwd, env, **_kwargs):
            user = Path(env["npm_config_userconfig"])
            global_config = Path(env["npm_config_globalconfig"])
            self.assertNotEqual(user, global_config)
            self.assertEqual((user.parent, global_config.parent), (cwd.resolve(), cwd.resolve()))
            self.assertEqual((user.read_bytes(), global_config.read_bytes()), (b"", b""))
            self.assertNotIn("NPM_CONFIG_USERCONFIG", env)
            package = _dsh_package(self.raw)
            _write(cwd / "package-lock.json", {"packages": {"": {"dependencies": package["dependencies"]}}})
            return type("Result", (), {"returncode": 0})()

        with patch.dict("os.environ", {"NPM_CONFIG_USERCONFIG": "/private/user-npmrc"}), \
             patch("bench.deepswe.cli.subprocess.run", side_effect=fake_npm):
            _prepare_dsh_lock(second_batch, self.raw)

    def test_generated_job_is_valid_for_fixed_pier_and_uses_one_trial_attempt(self) -> None:
        slot = schedule(self.raw)[0]
        attempt = self.batch / "attempt-001"
        task = self.batch / "task"
        job = JobConfig.model_validate(_job_config(self.batch, self.raw, slot, attempt, task))
        self.assertEqual(job.n_attempts, 1)
        self.assertEqual(job.n_concurrent_trials, 1)
        self.assertEqual(job.retry.max_retries, 0)
        self.assertEqual(job.agents[0].kwargs["arm"], slot["arm"])
        self.assertEqual(job.verifier.override_timeout_sec, self.raw["budget"]["verifier_timeout_sec"])
        self.assertEqual(job.environment.type, "docker")

    def test_run_requires_explicit_execute_and_check_does_not_start_pier(self) -> None:
        output, errors = StringIO(), StringIO()
        with patch("bench.deepswe.cli.load", return_value=self.raw), \
             patch("bench.deepswe.cli.subprocess.Popen", side_effect=AssertionError("Pier started")), \
             redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main(["check", "--manifest", str(self.batch / "plan.json")]), 0)
            self.assertEqual(main(["run", "--manifest", str(self.batch / "plan.json"),
                                   "--batch", str(self.batch / "output")]), 2)
        self.assertIn('"execution": "not started"', output.getvalue())
        self.assertIn("requires --execute", errors.getvalue())

    def test_legacy_search_toolset_cannot_start_a_real_batch(self) -> None:
        legacy = plan()
        legacy["conditions"]["toolset"] = "dsh-headless-default"
        errors = StringIO()
        with patch("bench.deepswe.cli.load", return_value=legacy), \
             patch("bench.deepswe.cli._freeze", side_effect=AssertionError("batch froze")), \
             redirect_stderr(errors):
            self.assertEqual(main(["run", "--manifest", str(self.batch / "plan.json"),
                                   "--batch", str(self.batch / "next"), "--execute"]), 2)
        self.assertIn("no-web-tools", errors.getvalue())

    def test_resume_skips_both_terminal_slots_without_creating_new_attempts(self) -> None:
        slots = schedule(self.raw)
        initial = [self.state(slot, "terminal") for slot in slots]
        with patch("bench.deepswe.cli._owned_containers", return_value=[]), \
             patch("bench.deepswe.cli._prepare_task", side_effect=AssertionError("terminal slot reran")):
            _execute_batch(self.batch, self.raw, resume=True)
        self.assertEqual([path.name for path in initial], ["attempt-001"] * len(slots))
        self.assertTrue(all(len(list(path.parent.glob("attempt-*"))) == 1 for path in initial))

    def test_running_host_process_blocks_same_slot_resume(self) -> None:
        first = schedule(self.raw)[0]
        old = self.state(first, "running")
        with patch("bench.deepswe.cli._active", return_value=True), \
             patch("bench.deepswe.cli._owned_containers", return_value=[]), \
             patch("bench.deepswe.cli._prepare_task", side_effect=AssertionError("concurrent restart")):
            with self.assertRaisesRegex(PlanError, "active Pier process"):
                _execute_batch(self.batch, self.raw, resume=True)
        self.assertEqual(len(list(old.parent.glob("attempt-*"))), 1)

    def test_running_orphan_container_blocks_resume_after_host_process_exits(self) -> None:
        first = schedule(self.raw)[0]
        old = self.state(first, "running")
        with patch("bench.deepswe.cli._active", return_value=False), \
             patch("bench.deepswe.cli._owned_containers", return_value=["owned-container"]), \
             patch("bench.deepswe.cli._prepare_task", side_effect=AssertionError("concurrent restart")):
            with self.assertRaisesRegex(PlanError, "active Docker containers"):
                _execute_batch(self.batch, self.raw, resume=True, retry_interrupted=True)
        self.assertEqual(len(list(old.parent.glob("attempt-*"))), 1)
        self.assertIn('"running"', (old / "state.json").read_text())

    def test_missing_trial_identity_does_not_certify_orphan_container_absent(self) -> None:
        first = schedule(self.raw)[0]
        old = self.state(first, "running", trial_identity=False)
        self.raw["budget"]["max_infrastructure_retries"] = 1
        with patch("bench.deepswe.cli._active", return_value=False), \
             patch("bench.deepswe.cli._spent", return_value=(0.0, True)), \
             patch("bench.deepswe.cli._prepare_task", side_effect=AssertionError("unconfirmed restart")):
            with self.assertRaises(PlanError):
                _execute_batch(self.batch, self.raw, resume=True, retry_interrupted=True)
        self.assertEqual(len(list(old.parent.glob("attempt-*"))), 1)

    def test_infrastructure_retry_requires_explicit_choice_and_preserves_original(self) -> None:
        first = schedule(self.raw)[0]
        old = self.state(first, "infrastructure_failure")
        self.raw["budget"]["max_infrastructure_retries"] = 1
        with patch("bench.deepswe.cli._owned_containers", return_value=[]), \
             patch("bench.deepswe.cli._prepare_task", side_effect=AssertionError("implicit retry")):
            with self.assertRaisesRegex(PlanError, "explicit, planned retry"):
                _execute_batch(self.batch, self.raw, resume=True)
        self.assertEqual(len(list(old.parent.glob("attempt-*"))), 1)
        self.assertEqual((old / "state.json").read_text().count("infrastructure_failure"), 1)

    def test_reverify_uses_saved_patch_in_new_trial_without_mutating_source(self) -> None:
        slot = schedule(self.raw)[0]
        source = self.batch / "slots" / slot["slot_id"] / "attempt-001"
        job_root = source / "pier-jobs" / "job"
        _write(job_root / "result.json", {"trial_results": []})
        trial = job_root / "trial"
        _write(trial / "result.json", {"agent_result": {"metadata": {"patch_status": "collected"}}})
        patch_file = trial / "agent" / "patch.diff"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text("saved patch bytes\n")
        with patch("bench.deepswe.cli._check_frozen", return_value=self.raw), \
             patch("bench.deepswe.cli._prepare_task", return_value=self.batch / "prepared-task"), \
             patch("bench.deepswe.cli._exec_job", return_value=0) as execute, \
             patch("bench.deepswe.cli._state_after", return_value="terminal"):
            first = _reverify(self.batch, slot["slot_id"], 1)
            second = _reverify(self.batch, slot["slot_id"], 1)
        self.assertNotEqual(first, second)
        self.assertEqual((first.name, second.name), ("replay-001", "replay-002"))
        self.assertEqual(patch_file.read_text(), "saved patch bytes\n")
        for call in execute.call_args_list:
            config = call.args[2]
            validated = JobConfig.model_validate(config)
            self.assertEqual(validated.agents[0].import_path, "bench.deepswe.agent:PatchReplayAgent")
            self.assertEqual(validated.agents[0].kwargs["patch_sha256"], digest(patch_file))
            self.assertEqual(validated.agents[0].env, {})


if __name__ == "__main__":
    unittest.main()
