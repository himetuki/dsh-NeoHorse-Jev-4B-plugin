"""Frozen conditions and arm configuration must agree before any trial starts."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bench.deepswe.config import FEATURES, LEGACY_TOOLSET, NO_WEB_TOOLSET, PlanError, digest, feature_settings, require_real_toolset, schedule, tree_digest, validate, validate_arm_settings
from bench.deepswe.profile import patch_rows


def plan() -> dict:
    return {
        "schema": 1,
        "phase": "pilot",
        "selection_rule": "Fixed two-task offline fixture, selected before results",
        "paths": {
            "deep_swe": "/fixture/deep-swe",
            "pier": "/fixture/pier",
            "plugin_tarball": "/fixture/jev.tgz",
        },
        "versions": {
            "dsh": "0.1.7-rc.2",
            "deep_swe_commit": "a" * 40,
            "pier_commit": "b" * 40,
            "plugin_tar_sha256": "c" * 64,
            "plugin_commit": "d" * 40,
            "node": "22.19.0",
            "pnpm": "11.7.0",
        },
        "model": {
            "provider": "fixture", "id": "scripted", "route": "fixture/scripted",
            "reasoning_effort": "high", "floating_alias": False,
            "endpoint": "http://127.0.0.1:5051/v1/chat/completions",
        },
        "jev": {
            "endpoint": "http://127.0.0.1:5050/v1/systemone",
            "model": "fixture-judge", "credential_env": "FIXTURE_JEV_KEY",
        },
        "conditions": {
            "main_credential_env": "FIXTURE_MAIN_KEY", "sandbox": "workspace-write",
            "toolset": NO_WEB_TOOLSET, "context_window": 368000,
            "compaction": "dsh-0.1.7-rc.2-default", "spill": "maxInlineTokens:12500",
            "network": "inference-and-npm-allowlist",
        },
        "budget": {
            "agent_timeout_sec": 60, "verifier_timeout_sec": 30,
            "cost_policy": "advisory", "max_batch_spend_usd": 1.0,
            "max_infrastructure_retries": 0, "usage_incomplete_policy": "halt",
        },
        "prices": {
            "main": {"source": "fixture-rate", "input_per_million": 1.0,
                     "cache_read_per_million": 0.2, "cache_write_per_million": 1.2,
                     "output_per_million": 2.0},
            "jev": {"source": "fixture-rate", "input_per_million": 0.5,
                    "cache_read_per_million": 0.0, "cache_write_per_million": 0.0,
                    "output_per_million": 1.0},
        },
        "arms": ["baseline", "log_admission"],
        "repeats": 2,
        "concurrency": 1,
        "tasks": [
            {"id": "task-a", "sha256": "1" * 64, "image_digest": "sha256:" + "2" * 64,
             "platform": "linux/amd64"},
            {"id": "task-b", "sha256": "3" * 64, "image_digest": "sha256:" + "4" * 64,
             "platform": "linux/amd64"},
        ],
    }


def discovered_fixture(home: Path, task_ids: tuple[str, ...]) -> tuple[dict, dict[str, Path]]:
    """Create local task definitions without pulling an image or running Pier."""
    raw = plan()
    deep = home / "deep-swe"
    pier = home / "pier"
    pier.mkdir()
    artifact = home / "plugin.tgz"
    artifact.write_bytes(b"offline fixture package")
    raw["paths"] = {"deep_swe": str(deep), "pier": str(pier), "plugin_tarball": str(artifact)}
    raw["versions"]["plugin_tar_sha256"] = digest(artifact)
    task_paths = {}
    raw["tasks"] = []
    for index, task_id in enumerate(task_ids):
        task = deep / "tasks" / task_id
        task.mkdir(parents=True)
        base = "a" * 40
        (task / "task.toml").write_text(
            '[metadata]\nbase_commit_hash = "' + base + '"\n'
            '[agent]\nnetwork_mode = "no-network"\n'
            '[verifier]\nenvironment_mode = "separate"\nnetwork_mode = "no-network"\n'
            '[verifier.environment]\ncpus = 1\n'
            '[[verifier.collect]]\ncommand = "git diff ' + base + ' HEAD"\n'
            '[environment]\ndocker_image = "fixture@sha256:abc"\n')
        raw["tasks"].append({"id": task_id, "sha256": tree_digest(task),
                             "image_digest": "sha256:" + f"{index + 1:064x}",
                             "platform": "linux/amd64"})
        task_paths[task_id] = task
    return raw, task_paths


class ConfigProfileAcceptance(unittest.TestCase):
    def test_declared_permission_modes_are_closed_and_pair_equal(self) -> None:
        raw = plan()
        for mode in ("workspace-write", "danger-full-access"):
            raw["conditions"]["sandbox"] = mode
            validate(raw, discover=False)
            baseline = [row for row in patch_rows(raw, "baseline") if row.get("id") != "jev"]
            enabled = [row for row in patch_rows(raw, "log_admission") if row.get("id") != "jev"]
            self.assertEqual(baseline, enabled)
        raw["conditions"]["sandbox"] = "read-only"
        with self.assertRaisesRegex(PlanError, "conditions.sandbox"):
            validate(raw, discover=False)

    def test_real_toolset_disables_web_consumer_and_legacy_remains_readable(self) -> None:
        raw = plan()
        for arm in ("baseline", "log_admission", "completion_check"):
            web = [row for row in patch_rows(raw, arm) if row.get("id") == "tool-web"]
            self.assertEqual(web, [{"id": "tool-web", "disabled": True}])
        require_real_toolset(raw)
        raw["conditions"]["toolset"] = LEGACY_TOOLSET
        validate(raw, discover=False)
        self.assertFalse(any(row.get("id") == "tool-web" for row in patch_rows(raw, "baseline")))
        with self.assertRaisesRegex(PlanError, "no-web-tools"):
            require_real_toolset(raw)

    def test_official_deepseek_route_binds_endpoint_key_reference_and_effort(self) -> None:
        raw = plan()
        raw["model"].update({"provider": "deepseek-official", "id": "deepseek-flash",
                             "route": "deepseek-official/deepseek-flash", "reasoning_effort": "high",
                             "endpoint": "https://api.deepseek.com/anthropic"})
        raw["conditions"]["main_credential_env"] = "DSH_EVAL_DEEPSEEK_KEY"
        validate(raw, discover=False)
        for arm in ("baseline", "log_admission"):
            provider = next(row for row in patch_rows(raw, arm) if row.get("id") == "llm-deepseek")
            self.assertEqual(provider["config"], {
                "baseURL": "https://api.deepseek.com/anthropic",
                "apiKeyEnv": "DSH_EVAL_DEEPSEEK_KEY", "reasoningEffort": "high",
            })
        raw["model"]["endpoint"] = "https://some-gateway.example/anthropic"
        with self.assertRaisesRegex(PlanError, "official Messages endpoint"):
            validate(raw, discover=False)

    def test_all_twelve_switches_are_exclusive_and_other_profile_rows_match(self) -> None:
        raw = plan()
        all_arms = ("baseline", "log_admission", "completion_check")
        feature_rows = {}
        other_rows = {}
        for arm in all_arms:
            features = feature_settings(arm)
            self.assertEqual(set(features), set(FEATURES))
            self.assertEqual(len(features), 12)
            self.assertFalse(features["stage-navigation"])
            validate_arm_settings(arm, features)
            rows = patch_rows(raw, arm, guard_path="/fixture/interaction_guard.mjs")
            jev_row = next(row for row in rows if row.get("id") == "jev")
            self.assertEqual(jev_row["config"]["features"], features)
            self.assertTrue(next(row for row in rows if row.get("id") == "session-title-llm")["disabled"])
            self.assertTrue(next(row for row in rows if row.get("id") == "jev-stage-navigation")["disabled"])
            feature_rows[arm] = features
            copy_rows = copy.deepcopy(rows)
            next(row for row in copy_rows if row.get("id") == "jev")["config"].pop("features")
            other_rows[arm] = copy_rows
        self.assertEqual(other_rows["baseline"], other_rows["log_admission"])
        self.assertEqual(other_rows["baseline"], other_rows["completion_check"])
        self.assertFalse(any(feature_rows["baseline"].values()))
        self.assertEqual({key for key, enabled in feature_rows["log_admission"].items() if enabled},
                         {"output-admission", "test-log-admission"})
        self.assertEqual({key for key, enabled in feature_rows["completion_check"].items() if enabled},
                         {"completion-check"})

    def test_configuration_drift_cannot_keep_the_old_arm_name(self) -> None:
        wrong = feature_settings("log_admission")
        wrong["completion-check"] = True
        with self.assertRaises(PlanError):
            validate_arm_settings("log_admission", wrong)

    def test_plan_rejects_missing_model_and_unsupported_hard_spend_cap(self) -> None:
        missing_model = plan()
        del missing_model["model"]["id"]
        with self.assertRaises(PlanError):
            validate(missing_model, discover=False)
        hard_cap = plan()
        hard_cap["budget"]["hard_usd_cap"] = 1.0
        with self.assertRaisesRegex(PlanError, "hard USD cap"):
            validate(hard_cap, discover=False)

    def test_pilot_rejects_completion_arm_and_duplicate_task_versions(self) -> None:
        with_completion = plan()
        with_completion["arms"].append("completion_check")
        with self.assertRaises(PlanError):
            validate(with_completion, discover=False)
        duplicate = plan()
        duplicate["tasks"].append(copy.deepcopy(duplicate["tasks"][0]))
        with self.assertRaises(PlanError):
            validate(duplicate, discover=False)

    def test_paired_schedule_balances_first_arm_before_results_exist(self) -> None:
        raw = validate(plan(), discover=False)
        slots = schedule(raw)
        self.assertEqual(len(slots), len(raw["tasks"]) * raw["repeats"] * len(raw["arms"]))
        self.assertEqual(len({slot["slot_id"] for slot in slots}), len(slots))
        pairs = {}
        for slot in slots:
            key = (slot["task_id"], slot["task_sha256"], slot["repeat"])
            pairs.setdefault(key, []).append(slot["arm"])
        self.assertTrue(all(set(arms) == set(raw["arms"]) for arms in pairs.values()))
        self.assertEqual(sum(arms[0] == "baseline" for arms in pairs.values()),
                         sum(arms[0] == "log_admission" for arms in pairs.values()))

    def test_discovery_rejects_public_agent_network_before_a_trial(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jev-eval-config-test-") as root:
            home = Path(root)
            deep = home / "deep-swe"
            task = deep / "tasks" / "task-a"
            task.mkdir(parents=True)
            pier = home / "pier"
            pier.mkdir()
            artifact = home / "plugin.tgz"
            artifact.write_bytes(b"offline fixture package")
            raw = plan()
            raw["paths"] = {"deep_swe": str(deep), "pier": str(pier),
                            "plugin_tarball": str(artifact)}
            raw["versions"]["plugin_tar_sha256"] = digest(artifact)
            raw["tasks"] = raw["tasks"][:1]
            definition = task / "task.toml"
            definition.write_text('[metadata]\nbase_commit_hash = "' + "a" * 40 + '"\n'
                                  '[agent]\nnetwork_mode = "no-network"\n'
                                  '[verifier]\nenvironment_mode = "separate"\nnetwork_mode = "no-network"\n'
                                  '[verifier.environment]\ncpus = 1\n'
                                  '[[verifier.collect]]\ncommand = "git diff ' + "a" * 40 + ' HEAD"\n'
                                  '[environment]\ndocker_image = "fixture@sha256:abc"\n')
            raw["tasks"][0]["sha256"] = tree_digest(task)
            with patch("bench.deepswe.config.git_head", side_effect=["a" * 40, "b" * 40]):
                validate(raw, discover=True)
            definition.write_text(definition.read_text().replace('[agent]\nnetwork_mode = "no-network"',
                                                                  '[agent]\nnetwork_mode = "public"'))
            raw["tasks"][0]["sha256"] = tree_digest(task)
            with patch("bench.deepswe.config.git_head", side_effect=["a" * 40, "b" * 40]):
                with self.assertRaisesRegex(PlanError, "no-network"):
                    validate(raw, discover=True)

    def test_nonfinite_cost_inputs_are_rejected_before_execution(self) -> None:
        for nonfinite in (float("nan"), float("inf"), float("-inf")):
            budget = plan()
            budget["budget"]["max_batch_spend_usd"] = nonfinite
            with self.subTest(field="batch budget", value=nonfinite), self.assertRaises(PlanError):
                validate(budget, discover=False)
            price = plan()
            price["prices"]["main"]["input_per_million"] = nonfinite
            with self.subTest(field="main price", value=nonfinite), self.assertRaises(PlanError):
                validate(price, discover=False)

    def test_first_of_two_smoke_init_scripts_is_checked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jev-eval-smoke-config-") as temporary:
            home = Path(temporary)
            raw, _ = discovered_fixture(home, ("smoke-one", "smoke-two"))
            raw["phase"] = "smoke"
            fixture = home / "model.mjs"
            fixture.write_text("export const name = 'fixture'\n")
            raw["model"].update(fixture_module=str(fixture), fixture_sha256=digest(fixture))
            for index, task in enumerate(raw["tasks"]):
                script = home / f"init-{index}.sh"
                script.write_text("#!/bin/sh\nexit 0\n")
                task.update(smoke_init_script=str(script), smoke_init_sha256=digest(script),
                            smoke_workdir="/app")
            raw["tasks"][0]["smoke_init_sha256"] = "0" * 64
            with self.assertRaisesRegex(PlanError, "smoke-one smoke init script changed"):
                validate(raw, discover=True)

    def test_formal_task_rejects_empty_verifier_collect(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jev-eval-formal-config-") as temporary:
            raw, task_paths = discovered_fixture(Path(temporary), ("formal-one",))
            raw["phase"] = "formal"
            definition = task_paths["formal-one"] / "task.toml"
            definition.write_text(definition.read_text().split('[[verifier.collect]]')[0] +
                                  '[environment]\ndocker_image = "fixture@sha256:abc"\n')
            raw["tasks"][0]["sha256"] = tree_digest(task_paths["formal-one"])
            with patch("bench.deepswe.config.git_head", side_effect=["a" * 40, "b" * 40]):
                with self.assertRaisesRegex(PlanError, "collect hook"):
                    validate(raw, discover=True)


if __name__ == "__main__":
    unittest.main()
