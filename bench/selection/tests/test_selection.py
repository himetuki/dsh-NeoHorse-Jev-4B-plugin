"""Keyless checks for the public glob selection suite."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bench.deepswe.config import FEATURES
from bench.selection.analyze import report_batch
from bench.selection.cases import CASE_ORDER, cases
from bench.selection.profile import selection_rows


class SelectionSuiteTests(unittest.TestCase):
    def test_frozen_case_counts_and_one_feature_difference(self) -> None:
        self.assertEqual([len(cases()[case]["files"]) for case in CASE_ORDER], [0, 1, 12, 16, 40, 41])
        plan = {
            "model": {"provider": "deepseek-official", "id": "deepseek-flash",
                      "reasoning_effort": "high", "endpoint": "https://api.deepseek.com/anthropic"},
            "jev": {"endpoint": "https://api.typesafe.ai/v1/systemone", "model": "jev-1.13.0",
                    "credential_env": "JEV_API_KEY"},
            "conditions": {"toolset": "dsh-headless-no-web-tools", "main_credential_env": "DEEPSEEK_API_KEY"},
        }
        baseline = selection_rows(plan, "baseline")
        treatment = selection_rows(plan, "file-ranking")
        feature = lambda rows: next(row["config"]["features"] for row in rows if row.get("id") == "jev")
        self.assertEqual(set(feature(baseline)), set(FEATURES))
        self.assertEqual(set(feature(treatment)), set(FEATURES))
        self.assertEqual([name for name in FEATURES if feature(baseline)[name] != feature(treatment)[name]],
                         ["file-ranking"])
        for rows in (baseline, treatment):
            self.assertIn({"id": "tool-web", "disabled": True}, rows)
            self.assertIn({"id": "jev-stage-navigation", "disabled": True}, rows)
            self.assertNotIn("disabled", next(row for row in rows if row.get("id") == "jev-selection"))

    def test_started_trial_without_result_keeps_cost_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            batch = Path(home)
            (batch / "jobs" / "zero" / "baseline").mkdir(parents=True)
            report = report_batch(batch, batch / "report.json")
            self.assertEqual(report["planned_trials"], 12)
            self.assertEqual(report["completed_trials"], 0)
            self.assertEqual(report["missing_cost_trials"], 1)
            self.assertEqual(report["known_estimated_usd"], 0)
            self.assertEqual(report["slots"][0]["status"], "started")
            self.assertFalse(report["slots"][0]["usage_complete"])
            self.assertEqual(report["slots"][1]["status"], "not-started")


if __name__ == "__main__":
    unittest.main()
