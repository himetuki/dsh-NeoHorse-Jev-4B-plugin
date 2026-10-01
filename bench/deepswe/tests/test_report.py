"""Reports preserve verifier outcomes, task denominators, and missing usage."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from bench.deepswe.config import feature_settings, schedule
from bench.deepswe.report import _paired, _participation, _search_usage, summarize
from bench.deepswe.tests.test_config_profile import plan


def write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def write_attempt(batch: Path, slot: dict, *, reward: int, termination: str = "normal",
                  main_usage: dict | None = None, failed_call_usage: dict | None = None,
                  compaction_usage: dict | None = None,
                  search_request_model: str | None = None,
                  jev_usage: dict | None = None, ledger_present: bool = True,
                  attempt_number: int = 1) -> None:
    attempt = batch / "slots" / slot["slot_id"] / f"attempt-{attempt_number:04d}"
    trial = attempt / "pier-jobs" / "job" / "trial"
    # Pier writes a job-level result beside one or more trial directories.
    write_json(attempt / "pier-jobs" / "job" / "result.json", {"trial_results": []})
    write_json(trial / "result.json", {
        "started_at": "2026-09-30T00:00:00+00:00",
        "finished_at": "2026-09-30T00:00:05+00:00",
        "agent_execution": {
            "started_at": "2026-09-30T00:00:01+00:00",
            "finished_at": "2026-09-30T00:00:03+00:00",
        },
        "agent_result": {"metadata": {"termination": termination, "patch_status": "collected",
                                      "evidence_export": "complete" if ledger_present else "failed"}},
    })
    write_json(trial / "verifier" / "reward.json", {
        "reward": reward, "f2p_passed": reward, "f2p_total": 1,
        "p2p_passed": 2, "p2p_total": 2, "apply_failed": 0,
    })
    session_id = f"session-{slot['slot_id']}-{attempt_number}"
    session = trial / "agent" / "dsh-home" / "sessions" / session_id / "session.v4.jsonl"
    # DSH 0.1.7-rc.2 Session v4 uses a physical header followed by event
    # envelopes; AgentLoop model messages have source.provider/model, and a
    # failed attempt's compact stream stores usage in a raw `chunk` record.
    rows = [{"type": "session", "version": 4, "id": session_id,
             "createdAt": 1790726400000, "isSeeded": False, "delegationDepth": 0}]
    message = {"role": "assistant", "source": {"provider": "fixture", "model": "scripted"},
               "content": [{"type": "text", "text": "Done"}]}
    settled = {"type": "assistant/message", "seq": 1, "at": 1790726401000,
               "data": {"turn": 1, "step": 1, "message": message}}
    if main_usage is not None:
        settled["data"]["usage"] = main_usage
    rows.append(settled)
    if failed_call_usage is not None:
        rows.append({"type": "assistant/attempt", "seq": 2, "at": 1790726401500,
                     "data": {"turn": 1, "step": 2, "stream": [
                         {"type": "chunk", "time": 1790726401400,
                          "chunk": {"type": "usage", "usage": failed_call_usage}},
                     ]}})
    if compaction_usage is not None:
        rows.append({"type": "compaction/summary", "seq": len(rows), "at": 1790726401700,
                     "data": {"usage": compaction_usage, "summary": "fixture summary"}})
    if search_request_model is not None:
        rows.append({"type": "web/deepseek-search-llm-request", "seq": len(rows), "at": 1790726401800,
                     "data": {"endpoint": "https://api.deepseek.com/anthropic/v1/messages",
                              "apiVersion": "2023-06-01", "body": {"model": search_request_model}}})
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    if ledger_present:
        storage = trial / "agent" / "dsh-home" / "storages"
        storage.mkdir(parents=True, exist_ok=True)
        write_json(trial / "agent" / "original-logs" / "index.json", [])
        if jev_usage is not None:
            write_json(storage / "jev_fixture" / "operations" / "op.json", {
                "version": 1,
                "record": {"id": "op", "featureId": "output-admission",
                           "sessionId": session_id, "status": "succeeded",
                           "attemptRecords": [{"id": "try-1", "status": "succeeded",
                                               "usage": jev_usage}],
                           "receipts": []},
            })


class ReportAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="jev-eval-report-test-")
        self.addCleanup(self.temp.cleanup)
        self.batch = Path(self.temp.name)

    def freeze(self, raw: dict) -> list[dict]:
        write_json(self.batch / "manifest.json", raw)
        return schedule(raw)

    def test_enabled_empty_ledger_is_zero_only_after_normal_complete_export(self) -> None:
        raw = plan()
        raw["tasks"] = raw["tasks"][:1]
        raw["repeats"] = 1
        slot = next(item for item in self.freeze(raw) if item["arm"] == "log_admission")
        usage = {"inputTokens": 10, "outputTokens": 5, "cacheReadTokens": 0, "cacheWriteTokens": 0}
        write_attempt(self.batch, slot, reward=1, main_usage=usage)
        trial = self.batch / "slots" / slot["slot_id"] / "attempt-0001" / "pier-jobs" / "job" / "trial"
        write_json(trial / "agent" / "jev-service-ready.json", {"features": feature_settings("log_admission")})
        complete = summarize(self.batch)["attempts"][0]
        self.assertTrue(complete["jev"]["storage_complete"])
        self.assertEqual(complete["jev"]["calls"], 0)
        self.assertEqual(complete["jev"]["estimated_usd"], 0)
        self.assertEqual(complete["total_estimated_usd"], complete["main"]["estimated_usd"])

        result_path = trial / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["agent_result"]["metadata"]["evidence_export"] = "failed"
        write_json(result_path, result)
        missing = summarize(self.batch)["attempts"][0]
        self.assertFalse(missing["jev"]["storage_complete"])
        self.assertIsNone(missing["jev"]["estimated_usd"])
        self.assertIsNone(missing["total_estimated_usd"])

        result["agent_result"]["metadata"]["evidence_export"] = "complete"
        write_json(result_path, result)
        (trial / "agent" / "original-logs" / "index.json").unlink()
        no_index = summarize(self.batch)["attempts"][0]
        self.assertIsNone(no_index["jev"]["estimated_usd"])

        write_json(trial / "agent" / "original-logs" / "index.json", [])
        result["agent_result"]["metadata"]["termination"] = "budget_exhausted"
        write_json(result_path, result)
        interrupted = summarize(self.batch)["attempts"][0]
        self.assertIsNone(interrupted["jev"]["estimated_usd"])

        result["agent_result"]["metadata"]["termination"] = "normal"
        write_json(result_path, result)
        invalid = trial / "agent" / "dsh-home" / "storages" / "jev_fixture" / "operations" / "op.json"
        invalid.parent.mkdir(parents=True, exist_ok=True)
        invalid.write_text("{invalid json}\n", encoding="utf-8")
        corrupt = summarize(self.batch)["attempts"][0]
        self.assertEqual(corrupt["jev"]["invalid_record_files"], 1)
        self.assertIsNone(corrupt["jev"]["estimated_usd"])

        invalid.unlink()
        invalid.parent.rmdir()
        invalid.parent.parent.rmdir()
        invalid.parent.parent.parent.rmdir()
        no_storage = summarize(self.batch)["attempts"][0]
        self.assertIsNone(no_storage["jev"]["estimated_usd"])

    def test_legacy_search_request_keeps_known_subtotal_but_total_unknown(self) -> None:
        raw = plan()
        raw["conditions"]["toolset"] = "dsh-headless-default"
        raw["tasks"] = raw["tasks"][:1]
        raw["repeats"] = 1
        slot = next(item for item in self.freeze(raw) if item["arm"] == "baseline")
        write_attempt(self.batch, slot, reward=0,
                      main_usage={"inputTokens": 100, "outputTokens": 20,
                                  "cacheReadTokens": 0, "cacheWriteTokens": 0},
                      search_request_model="deepseek-v4-flash")
        agent = self.batch / "slots" / slot["slot_id"] / "attempt-0001" / "pier-jobs" / "job" / "trial" / "agent"
        write_json(agent / "jev-service-ready.json", {"features": feature_settings("baseline")})
        report = summarize(self.batch)
        row = report["attempts"][0]
        self.assertEqual(row["search"]["recorded_requests"], 1)
        self.assertEqual(row["search"]["models"], ["deepseek-v4-flash"])
        self.assertIsNone(row["search"]["confirmed_responses"])
        self.assertIsNone(row["search"]["estimated_usd"])
        self.assertIsNone(row["total_estimated_usd"])
        self.assertEqual(row["known_estimated_subtotal_usd"], row["main"]["estimated_usd"])
        self.assertEqual(report["known_estimated_cost_usd"], row["main"]["estimated_usd"])
        self.assertEqual(report["missing_cost_attempts"], 1)
        self.assertFalse(report["cost_complete"])
        self.assertEqual(_search_usage([])["estimated_usd"], 0)

    def test_timeout_reward_is_not_normal_completion_and_missing_usage_stays_unknown(self) -> None:
        raw = plan()
        raw["repeats"] = 1
        slots = self.freeze(raw)
        ordinary = {"inputTokens": 100, "outputTokens": 50, "cacheReadTokens": 20,
                    "cacheWriteTokens": 0, "reasoningTokens": 10}
        failed = {"inputTokens": 40, "outputTokens": 12, "cacheReadTokens": 0,
                  "cacheWriteTokens": 0, "reasoningTokens": 4}
        for slot in slots:
            if slot["task_id"] == "task-a" and slot["arm"] == "baseline":
                write_attempt(self.batch, slot, reward=1, main_usage=ordinary)
            elif slot["task_id"] == "task-a":
                write_attempt(self.batch, slot, reward=1, termination="budget_exhausted",
                              main_usage=ordinary, failed_call_usage=failed,
                              jev_usage={"inputTokens": 10, "outputTokens": 5})
            elif slot["arm"] == "baseline":
                write_attempt(self.batch, slot, reward=0, main_usage=ordinary)
            else:
                write_attempt(self.batch, slot, reward=1, main_usage=None, ledger_present=False)
        report = summarize(self.batch)
        self.assertEqual(report["planned_slots"], 4)
        self.assertEqual(report["by_arm"]["log_admission"]["reward_1"], 2)
        self.assertEqual(report["by_arm"]["log_admission"]["normal_unassisted_solved"], 1)
        self.assertFalse(report["cost_complete"])
        rows = {(row["slot"]["task_id"], row["slot"]["arm"]): row for row in report["attempts"]}
        timed = rows[("task-a", "log_admission")]
        self.assertEqual(timed["termination"], "budget_exhausted")
        self.assertEqual(timed["main"]["calls"], 2)
        self.assertEqual(timed["main"]["inputTokens"], 140)
        self.assertEqual(timed["main"]["outputTokens"], 62)
        self.assertEqual(timed["jev"]["calls"], 1)
        self.assertEqual(timed["jev"]["inputTokens"], 10)
        missing = rows[("task-b", "log_admission")]
        self.assertIsNone(missing["main"]["estimated_usd"])
        self.assertIsNone(missing["jev"]["estimated_usd"])
        self.assertIsNone(missing["total_estimated_usd"])
        paired = report["paired"]["comparisons"]["log_admission"]
        self.assertEqual((paired["planned_tasks"], paired["fully_paired_tasks"]), (2, 2))
        self.assertEqual((paired["wins"], paired["losses"], paired["ties"]), (1, 0, 1))

    def test_three_arms_keep_both_treatment_comparisons_and_missing_pair_denominator(self) -> None:
        raw = plan()
        raw["phase"] = "formal"
        raw["arms"] = ["baseline", "log_admission", "completion_check"]
        raw["repeats"] = 1
        slots = self.freeze(raw)
        usage = {"inputTokens": 20, "outputTokens": 10, "cacheReadTokens": 0,
                 "cacheWriteTokens": 0}
        for slot in slots:
            if slot["task_id"] == "task-b" and slot["arm"] == "completion_check":
                continue
            reward = 1 if slot["arm"] == "completion_check" else 0
            write_attempt(self.batch, slot, reward=reward, main_usage=usage,
                          jev_usage={"inputTokens": 2, "outputTokens": 1}
                          if slot["arm"] != "baseline" else None)
        comparisons = summarize(self.batch)["paired"]["comparisons"]
        self.assertEqual(set(comparisons), {"log_admission", "completion_check"})
        self.assertEqual(comparisons["log_admission"]["fully_paired_tasks"], 2)
        self.assertEqual(comparisons["completion_check"]["planned_tasks"], 2)
        self.assertEqual(comparisons["completion_check"]["fully_paired_tasks"], 1)
        self.assertEqual(comparisons["completion_check"]["missing_pair_tasks"], 1)

    def test_excluding_two_unscorable_tasks_changes_denominator_and_mean_together(self) -> None:
        raw = plan()
        raw["repeats"] = 1
        raw["tasks"] = [
            {"id": f"case-{index}", "sha256": f"{index:064x}",
             "image_digest": "sha256:" + "a" * 64, "platform": "linux/amd64"}
            for index in range(17)
        ]
        rows = []
        for slot in schedule(raw):
            case = int(slot["task_id"].split("-")[1])
            reward = (1 if case == 2 else 0) if slot["arm"] == "baseline" else (1 if case in (0, 1) else 0)
            rows.append({"slot": slot, "scorable": True, "termination": "normal",
                         "verifier": {"reward": reward, "f2p_passed": reward,
                                      "f2p_total": 1, "p2p_passed": 1, "p2p_total": 1}})
        whole = _paired(raw, rows)["comparisons"]["log_admission"]
        self.assertEqual((whole["planned_tasks"], whole["fully_paired_tasks"]), (17, 17))
        self.assertEqual((whole["wins"], whole["losses"], whole["ties"]), (2, 1, 14))
        self.assertAlmostEqual(whole["mean_reward_delta"], 1 / 17)
        incomplete = [copy.deepcopy(row) for row in rows]
        for row in incomplete:
            if row["slot"]["task_id"] in ("case-15", "case-16") and row["slot"]["arm"] == "log_admission":
                row["scorable"] = False
        conditional = _paired(raw, incomplete)["comparisons"]["log_admission"]
        self.assertEqual((conditional["planned_tasks"], conditional["fully_paired_tasks"],
                         conditional["missing_pair_tasks"]), (17, 15, 2))
        self.assertEqual((conditional["wins"], conditional["losses"], conditional["ties"]), (2, 1, 12))
        self.assertAlmostEqual(conditional["mean_reward_delta"], 1 / 15)

    def test_all_preplanned_repeats_contribute_before_task_level_pairing(self) -> None:
        raw = plan()
        raw["phase"] = "formal"
        raw["tasks"] = raw["tasks"][:1]
        raw["repeats"] = 3
        rows = []
        for slot in schedule(raw):
            reward = int(slot["arm"] == "log_admission" and slot["repeat"] == 2)
            rows.append({"slot": slot, "scorable": True, "termination": "normal",
                         "verifier": {"reward": reward, "f2p_passed": reward,
                                      "f2p_total": 1, "p2p_passed": 1, "p2p_total": 1}})
        paired = _paired(raw, rows)["comparisons"]["log_admission"]
        self.assertEqual((paired["planned_tasks"], paired["fully_paired_tasks"]), (1, 1))
        self.assertEqual((paired["wins"], paired["losses"], paired["ties"]), (1, 0, 0))
        self.assertAlmostEqual(paired["mean_reward_delta"], 1 / 3)

    def test_finished_agent_without_verifier_reward_is_terminal_but_not_solved(self) -> None:
        raw = plan()
        raw["tasks"] = raw["tasks"][:1]
        raw["repeats"] = 1
        slots = self.freeze(raw)
        slot = slots[0]
        write_attempt(self.batch, slot, reward=1, main_usage={
            "inputTokens": 1, "outputTokens": 1, "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
        })
        reward = self.batch / "slots" / slot["slot_id"] / "attempt-0001" / "pier-jobs" / "job" / "trial" / "verifier" / "reward.json"
        reward.unlink()
        report = summarize(self.batch)
        row = report["attempts"][0]
        self.assertEqual(row["termination"], "normal")
        self.assertFalse(row["scorable"])
        self.assertIsNone(row["verifier"]["reward"])
        self.assertEqual(report["by_arm"][slot["arm"]]["normal_unassisted_solved"], 0)
        self.assertEqual(report["paired"]["comparisons"]["log_admission"]["fully_paired_tasks"], 0)

    def test_pier_environment_failure_without_trial_result_stays_in_attempt_denominator(self) -> None:
        raw = plan()
        raw["tasks"] = raw["tasks"][:1]
        raw["repeats"] = 1
        slots = self.freeze(raw)
        failed = next(slot for slot in slots if slot["arm"] == "baseline")
        failed_attempt = self.batch / "slots" / failed["slot_id"] / "attempt-001"
        write_json(failed_attempt / "state.json", {"status": "infrastructure_failure",
                                                  "pier_exit_code": 1})
        completed = next(slot for slot in slots if slot["arm"] == "log_admission")
        write_attempt(self.batch, completed, reward=1, main_usage={
            "inputTokens": 1, "outputTokens": 1, "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
        }, jev_usage={"inputTokens": 1, "outputTokens": 1})
        write_json(self.batch / "slots" / completed["slot_id"] / "attempt-0001" / "state.json",
                   {"status": "terminal", "pier_exit_code": 0})
        report = summarize(self.batch)
        self.assertEqual(report["planned_slots"], 2)
        self.assertEqual(report["attempted_slots"], 2)
        self.assertEqual(report["scored_slots"], 1)
        self.assertEqual(report["infrastructure_failure_attempts"], 1)
        self.assertEqual(report["infrastructure_failure_rate_per_attempt"], 0.5)
        self.assertEqual(report["by_arm"]["baseline"]["infrastructure_failures"], 1)
        self.assertEqual(report["paired"]["comparisons"]["log_admission"]["fully_paired_tasks"], 0)

    def test_compaction_model_call_is_charged_as_main_model_usage(self) -> None:
        raw = plan()
        raw["tasks"] = raw["tasks"][:1]
        raw["repeats"] = 1
        slots = self.freeze(raw)
        first = slots[0]
        write_attempt(self.batch, first, reward=0,
                      main_usage={"inputTokens": 100, "outputTokens": 40,
                                  "cacheReadTokens": 0, "cacheWriteTokens": 0},
                      compaction_usage={"inputTokens": 30, "outputTokens": 10,
                                        "cacheReadTokens": 0, "cacheWriteTokens": 0})
        row = summarize(self.batch)["attempts"][0]
        self.assertEqual(row["main"]["calls"], 2)
        self.assertEqual(row["main"]["inputTokens"], 130)
        self.assertEqual(row["main"]["outputTokens"], 50)

    def test_log_adoption_and_completion_execution_are_distinct_from_judgments(self) -> None:
        final = "Kept summary\n[Jev original log: locator]"
        events = [
            {"type": "tool/result", "data": {"message": {
                "source": {"kind": "tool", "callId": "tool-1"},
                "content": [{"type": "text", "text": final}],
            }}},
            {"type": "user/message", "data": {"message": {
                "source": {"kind": "jev-supervision", "action": "supplement"},
                "content": [{"type": "text", "text": "Complete omission once"}],
            }}},
            {"type": "assistant/message", "data": {"message": {
                "source": {"provider": "fixture", "model": "scripted"},
                "content": [{"type": "text", "text": "Supplement done"}],
            }}},
        ]
        operations = [
            {"featureId": "output-admission", "status": "succeeded", "link": {"inputVersion": "tool-1"},
             "attemptRecords": [{"status": "succeeded"}],
             "receipts": [{"id": "tool-log-final-result", "status": "observed",
                           "reason": json.dumps({"inputChars": 500, "locator": "locator"})}]},
            {"featureId": "output-admission", "status": "succeeded", "attemptRecords": [{"status": "succeeded"}],
             "receipts": []},
            {"featureId": "output-admission", "status": "failed", "attemptRecords": [{"status": "failed"}],
             "receipts": []},
            {"featureId": "completion-check", "status": "succeeded", "attemptRecords": [{"status": "succeeded"}],
             "receipts": [{"id": "supplement-queued", "status": "executed"}]},
        ]
        participation = _participation(self.batch, events, operations)
        logs = participation["output-admission"]
        self.assertEqual((logs["judgments"], logs["adopted"], logs["retained"], logs["fallbacks"]),
                         (3, 1, 1, 1))
        completion = participation["completion-check"]
        self.assertEqual((completion["supplement_queued"], completion["supplement_delivered"],
                          completion["supplement_acted"]), (1, 1, 1))
        queued_only = _participation(self.batch, [], operations)["completion-check"]
        self.assertEqual((queued_only["supplement_queued"], queued_only["supplement_delivered"],
                          queued_only["supplement_acted"]), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
