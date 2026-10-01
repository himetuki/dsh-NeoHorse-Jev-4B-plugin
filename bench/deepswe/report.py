"""Read pinned DSH/Pier evidence and summarize task-level paired outcomes."""

from __future__ import annotations

import json
import random
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import feature_settings, load, schedule


def _json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _timing(value: Any) -> float | None:
    if not isinstance(value, dict) or not value.get("started_at") or not value.get("finished_at"):
        return None
    try:
        start = datetime.fromisoformat(value["started_at"].replace("Z", "+00:00"))
        finish = datetime.fromisoformat(value["finished_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return max(0.0, (finish - start).total_seconds())


def _usage_cost(usages: list[dict[str, Any]], price: dict[str, Any], *, jev: bool = False) -> dict[str, Any]:
    fields = ("inputTokens", "outputTokens") if jev else ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens")
    result: dict[str, Any] = {"calls": len(usages), "complete": True, "missing_calls": 0}
    for field in fields:
        present = [usage.get(field) for usage in usages]
        if any(type(value) is not int or value < 0 for value in present):
            result[field] = None
            result["complete"] = False
        else:
            result[field] = sum(present)
    result["missing_calls"] = sum(1 for usage in usages if any(type(usage.get(field)) is not int for field in ("inputTokens", "outputTokens")))
    if jev:
        result["cacheReadTokens"] = 0
        result["cacheWriteTokens"] = 0
    if result["complete"]:
        result["estimated_usd"] = (
            result["inputTokens"] * price["input_per_million"]
            + result["cacheReadTokens"] * price["cache_read_per_million"]
            + result["cacheWriteTokens"] * price["cache_write_per_million"]
            + result["outputTokens"] * price["output_per_million"]
        ) / 1_000_000
    else:
        result["estimated_usd"] = None
    result["price_source"] = price["source"]
    return result


def _session(agent_dir: Path) -> tuple[str | None, list[dict[str, Any]] | None, str | None]:
    sessions = list((agent_dir / "dsh-home" / "sessions").rglob("session.v4.jsonl"))
    if len(sessions) != 1:
        return None, None, "expected exactly one uncompressed Session v4"
    try:
        rows = [json.loads(line) for line in sessions[0].read_text(encoding="utf-8").splitlines() if line]
    except (OSError, ValueError):
        return None, None, "Session JSONL cannot be read"
    if not rows or rows[0].get("type") != "session" or rows[0].get("version") != 4 or not isinstance(rows[0].get("id"), str):
        return None, None, "Session format or header is unsupported"
    return rows[0]["id"], rows[1:], None


def _model_usage(events: list[dict[str, Any]] | None, session_id: str | None, price: dict[str, Any],
                 model: dict[str, Any]) -> dict[str, Any]:
    if events is None:
        return {"calls": None, "complete": False, "estimated_usd": None, "missing_calls": None, "price_source": price["source"]}
    usages: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") == "assistant/message":
            data = event.get("data") or {}
            source = (data.get("message") or {}).get("source") or {}
            if source.get("provider") != model["provider"] or source.get("model") != model["id"]:
                continue
            usages.append(data.get("usage") if isinstance(data.get("usage"), dict) else {})
        elif event.get("type") == "assistant/attempt":
            data = event.get("data") or {}
            # Failed/cancelled attempts do not have an assistant/message. The
            # stream's last usage chunk is one call, never another copy of a
            # settled assistant/message stream.
            stream = data.get("stream") or []
            usage = [item.get("chunk", {}).get("usage") for item in stream if item.get("chunk", {}).get("type") == "usage"]
            usages.append(usage[-1] if usage and isinstance(usage[-1], dict) else {})
        elif event.get("type") == "compaction/summary":
            summary_usage = (event.get("data") or {}).get("usage")
            usages.append(summary_usage if isinstance(summary_usage, dict) else {})
    result = _usage_cost(usages, price)
    result["session_id"] = session_id
    return result


def _search_usage(events: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Identify auxiliary search requests without inventing response usage."""
    if events is None:
        return {"recorded_requests": None, "models": None, "endpoints": None,
                "confirmed_responses": None, "estimated_usd": None, "complete": False}
    requests = [event.get("data") or {} for event in events
                if event.get("type") == "web/deepseek-search-llm-request"]
    return {"recorded_requests": len(requests),
            "models": sorted({body.get("model") for item in requests
                              if isinstance(body := item.get("body"), dict) and isinstance(body.get("model"), str)}),
            "endpoints": sorted({item["endpoint"] for item in requests if isinstance(item.get("endpoint"), str)}),
            "confirmed_responses": None if requests else 0,
            "estimated_usd": None if requests else 0,
            "complete": not requests}


def _ledger(agent_dir: Path, session_id: str | None, price: dict[str, Any], arm: str,
            metadata: dict[str, Any], termination: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    storage = agent_dir / "dsh-home" / "storages"
    domains = list(storage.glob("jev_*/operations"))
    files = [file for domain in domains for file in domain.glob("*.json")]
    operations: list[dict[str, Any]] = []
    invalid_files = 0
    for file in files:
        stored = _json(file)
        detail = stored.get("record") if stored else None
        if not isinstance(detail, dict):
            invalid_files += 1
        elif (detail.get("sessionId") or (detail.get("link") or {}).get("sessionId")) == session_id:
            operations.append(detail)
    attempts = [attempt for operation in operations for attempt in operation.get("attemptRecords", []) if isinstance(attempt, dict)]
    usages = [attempt.get("usage") if isinstance(attempt.get("usage"), dict) else {} for attempt in attempts]
    result = _usage_cost(usages, price, jev=True)
    result["operations"] = len(operations)
    result["failed_attempts"] = sum(1 for attempt in attempts if attempt.get("status") != "succeeded")
    ready = _json(agent_dir / "jev-service-ready.json")
    verified_ready = ready is not None and ready.get("features") == feature_settings(arm)
    try:
        original_index = json.loads((agent_dir / "original-logs" / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        original_index = None
    index_valid = isinstance(original_index, list) and all(isinstance(row, dict) for row in original_index)
    empty_export = termination == "normal" and not domains and not files and original_index == []
    result["storage_complete"] = (session_id is not None and verified_ready and
                                   metadata.get("evidence_export") == "complete" and storage.is_dir() and
                                   index_valid and invalid_files == 0 and
                                   ((len(domains) == 1 and bool(files)) or empty_export))
    result["service_ready"] = verified_ready
    result["invalid_record_files"] = invalid_files
    if not result["storage_complete"]:
        result["complete"] = False
        result["estimated_usd"] = None
    return result, operations


def _text_content(event: dict[str, Any]) -> str:
    message = (event.get("data") or {}).get("message") or {}
    return "\n".join(block.get("text", "") for item in message.get("content", []) if isinstance(item, dict)
                     for block in (item.get("content", []) if item.get("type") == "tool-result" else [item])
                     if isinstance(block, dict) and block.get("type") == "text")


def _participation(agent_dir: Path, events: list[dict[str, Any]] | None,
                   operations: list[dict[str, Any]]) -> dict[str, Any]:
    original_index_path = agent_dir / "original-logs" / "index.json"
    try:
        original_index = json.loads(original_index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        original_index = []
    saved_originals = {row.get("operationId"): row for row in original_index if isinstance(row, dict) and row.get("status") == "saved"}
    tool_results: dict[str, str] = {}
    tool_result_positions: dict[str, int] = {}
    tool_calls: list[tuple[int, str, str]] = []
    supplement_steps: list[int] = []
    assistant_steps: list[int] = []
    for index, event in enumerate(events or []):
        kind = event.get("type")
        message = (event.get("data") or {}).get("message") or {}
        source = message.get("source") or {}
        if kind == "tool/result" and source.get("kind") == "tool":
            tool_results[source.get("callId", "")] = _text_content(event)
            tool_result_positions[source.get("callId", "")] = index
        if kind == "user/message" and source.get("kind") == "jev-supervision" and source.get("action") == "supplement":
            supplement_steps.append(index)
        if kind == "assistant/message":
            assistant_steps.append(index)
            for block in message.get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool-call":
                    tool_calls.append((index, block.get("id", ""), str(block.get("arguments", ""))))
    by_feature: dict[str, dict[str, Any]] = {}
    for feature in ("output-admission", "test-log-admission", "completion-check"):
        records = [op for op in operations if op.get("featureId") == feature]
        receipts = [receipt for op in records for receipt in op.get("receipts", []) if isinstance(receipt, dict)]
        value: dict[str, Any] = {"eligible": None, "judgments": sum(len(op.get("attemptRecords", [])) for op in records),
                                 "operations": len(records), "retained": None, "fallbacks": None,
                                 "adopted": None, "unobservable": []}
        if feature in ("output-admission", "test-log-admission"):
            reductions = []
            for op in records:
                receipt = next((item for item in op.get("receipts", []) if item.get("id") == "tool-log-final-result"), None)
                if receipt is None:
                    continue
                try:
                    detail = json.loads(receipt.get("reason") or "")
                except ValueError:
                    continue
                call_id = (op.get("link") or {}).get("inputVersion")
                final = tool_results.get(call_id)
                if final is None:
                    continue
                original = saved_originals.get(op.get("id"), {})
                relative = original.get("relativePath", "") if original else ""
                saved = agent_dir / relative if isinstance(relative, str) and relative.startswith("original-logs/") and ".." not in Path(relative).parts else None
                verified = saved is not None and saved.is_file() and hashlib.sha256(saved.read_bytes()).hexdigest() == original.get("sha256")
                readback = False
                if verified:
                    source_text = saved.read_text(encoding="utf-8")
                    readback = any(locator in args and position > tool_result_positions.get(call_id, -1)
                                   and source_text.rstrip() in tool_results.get(other_call, "")
                                   for position, other_call, args in tool_calls
                                   for locator in [detail.get("locator")]
                                   if isinstance(locator, str))
                reductions.append({"call_id": call_id, "original_chars": detail.get("inputChars"),
                                   "final_chars": len(final), "locator": detail.get("locator"),
                                   "recovery_reference_visible": "[Jev original log:" in final,
                                   "original_saved_and_hashed": verified,
                                   "agent_readback_verified": readback})
            value["adopted"] = sum(1 for row in reductions if isinstance(row["original_chars"], int)
                                   and row["final_chars"] < row["original_chars"] and row["recovery_reference_visible"])
            value["reductions"] = reductions
            value["recoverable_adoptions"] = sum(row["original_saved_and_hashed"] for row in reductions if
                isinstance(row["original_chars"], int) and row["final_chars"] < row["original_chars"] and row["recovery_reference_visible"])
            value["agent_readbacks"] = sum(row["agent_readback_verified"] for row in reductions)
            value["unobservable"] = ["eligible candidates"]
            value["retained"] = sum(1 for op in records if op.get("status") == "succeeded") - value["adopted"]
            value["fallbacks"] = sum(1 for op in records if op.get("status") in ("failed", "cancelled"))
        else:
            queued = sum(1 for receipt in receipts if receipt.get("id") == "supplement-queued" and receipt.get("status") == "executed")
            value.update({"supplement_queued": queued, "supplement_delivered": len(supplement_steps),
                          "supplement_acted": sum(any(assistant > step for assistant in assistant_steps) for step in supplement_steps),
                          "unobservable": ["whether the supplement caused a passing test"]})
        by_feature[feature] = value
    return by_feature


def _one_attempt(path: Path, slot: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    jobs_root = path / "pier-jobs"
    pier_jobs = [file for file in jobs_root.rglob("result.json") if len(file.relative_to(jobs_root).parts) == 3]
    result = _json(pier_jobs[0]) if len(pier_jobs) == 1 else None
    runner_state = _json(path / "state.json") or {}
    trial = pier_jobs[0].parent if len(pier_jobs) == 1 else None
    agent_dir = trial / "agent" if trial else path / "agent"
    verifier_dir = trial / "verifier" if trial else path / "verifier"
    reward = _json(verifier_dir / "reward.json")
    reward_text = verifier_dir / "reward.txt"
    verifier_sentinel = reward_text.is_file() and reward_text.read_text(encoding="utf-8").strip() == "-1"
    metadata = ((result or {}).get("agent_result") or {}).get("metadata") or {}
    exception = ((result or {}).get("exception_info") or {}).get("exception_type")
    termination = metadata.get("termination", "unknown")
    if exception == "AgentTimeoutError":
        termination = "budget_exhausted"
    elif exception == "CancelledError" and termination == "running":
        termination = "interrupted"
    interactions = agent_dir / "interactions.jsonl"
    if interactions.is_file() and interactions.stat().st_size:
        termination = "needs-human"
    session_id, events, session_error = _session(agent_dir)
    main = _model_usage(events, session_id, plan["prices"]["main"], plan["model"])
    search = _search_usage(events)
    jev, operations = _ledger(agent_dir, session_id, plan["prices"]["jev"], slot["arm"], metadata, termination)
    if slot["arm"] == "baseline" and jev["operations"] == 0 and jev["storage_complete"]:
        jev.update({"calls": 0, "inputTokens": 0, "outputTokens": 0, "estimated_usd": 0, "complete": True})
    metrics = {key: reward.get(key) if reward else None for key in
               ("reward", "f2p_passed", "f2p_total", "p2p_passed", "p2p_total", "apply_failed")}
    reward_value = metrics["reward"]
    scorable = reward_value in (0, 1) and all(type(metrics[key]) is int for key in
                   ("f2p_passed", "f2p_total", "p2p_passed", "p2p_total"))
    known_components = [value for value in (main.get("estimated_usd"), jev.get("estimated_usd"),
                                             search.get("estimated_usd")) if value is not None]
    known_cost = len(known_components) == 3
    return {
        "slot": slot, "attempt_dir": str(path), "trial_result": str(pier_jobs[0]) if trial else None,
        "termination": termination, "runner_status": runner_state.get("status", "unknown"),
        "pier_exception": exception, "patch_status": metadata.get("patch_status"),
        "session_id": session_id, "session_error": session_error, "verifier": metrics,
        "scorable": scorable, "verifier_infrastructure_sentinel": verifier_sentinel,
        "agent_seconds": _timing((result or {}).get("agent_execution")),
        "trial_seconds": _timing(result), "main": main, "jev": jev, "search": search,
        "known_estimated_subtotal_usd": sum(known_components),
        "total_estimated_usd": sum(known_components) if known_cost else None,
        "participation": _participation(agent_dir, events, operations),
    }


def attempt_rows(batch: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan = load(batch / "manifest.json", discover=False)
    index = {slot["slot_id"]: slot for slot in schedule(plan)}
    rows = []
    for slot_id, slot in index.items():
        slot_dir = batch / "slots" / slot_id
        for attempt in sorted(slot_dir.glob("attempt-*")):
            rows.append(_one_attempt(attempt, slot, plan))
    return plan, rows


def _paired(plan: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    final: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in rows:
        slot = row["slot"]
        final[(slot["task_id"], slot["repeat"], slot["arm"])] = row
    task_rows = []
    for task in plan["tasks"]:
        by_arm = {}
        for arm in plan["arms"]:
            values = [final.get((task["id"], repeat, arm)) for repeat in range(plan["repeats"])]
            scored = [row for row in values if row and row["scorable"]]
            f2p = [row["verifier"]["f2p_passed"] / row["verifier"]["f2p_total"] for row in scored
                   if row["verifier"]["f2p_total"] > 0]
            by_arm[arm] = {"planned": plan["repeats"], "scored": len(scored), "missing": plan["repeats"] - len(scored),
                           "reward_mean": sum(row["verifier"]["reward"] for row in scored) / len(scored) if scored else None,
                           "f2p_mean": sum(f2p) / len(f2p) if len(f2p) == len(scored) and f2p else None,
                           "p2p_regressions": sum(row["verifier"]["p2p_passed"] < row["verifier"]["p2p_total"] for row in scored),
                           "normal_unassisted_solved": sum(row["termination"] == "normal" and row["verifier"]["reward"] == 1 for row in scored)}
        task_rows.append({"task_id": task["id"], "by_arm": by_arm})
    comparisons = {}
    for treatment in (arm for arm in plan["arms"] if arm != "baseline"):
        paired_rows = []
        for row in task_rows:
            left, right = row["by_arm"]["baseline"], row["by_arm"][treatment]
            if left["scored"] == right["scored"] == plan["repeats"]:
                paired_rows.append({"task_id": row["task_id"],
                                    "reward_delta": right["reward_mean"] - left["reward_mean"],
                                    "f2p_delta": right["f2p_mean"] - left["f2p_mean"] if left["f2p_mean"] is not None and right["f2p_mean"] is not None else None})
        deltas = [row["reward_delta"] for row in paired_rows]
        rng = random.Random(0)
        boots = [sum(rng.choice(deltas) for _ in deltas) / len(deltas) for _ in range(2000)] if deltas else []
        boots.sort()
        low, high = (boots[49], boots[1949]) if boots else (None, None)
        comparisons[treatment] = {"paired_tasks": paired_rows, "planned_tasks": len(task_rows),
            "fully_paired_tasks": len(paired_rows), "missing_pair_tasks": len(task_rows) - len(paired_rows),
            "wins": sum(delta > 0 for delta in deltas), "losses": sum(delta < 0 for delta in deltas),
            "ties": sum(delta == 0 for delta in deltas),
            "mean_reward_delta": sum(deltas) / len(deltas) if deltas else None,
            "task_bootstrap_95": [low, high],
            "interpretation": "exploratory paired estimate; benefit not established without prespecified effect and participation criteria"}
    return {"tasks": task_rows, "comparisons": comparisons}


def summarize(batch: Path) -> dict[str, Any]:
    """Produce an incomplete report when evidence is missing; never impute usage."""
    plan, rows = attempt_rows(batch)
    slots = schedule(plan)
    complete = {row["slot"]["slot_id"] for row in rows if row["scorable"]}
    costs = [row["total_estimated_usd"] for row in rows]
    known_cost = sum(row["known_estimated_subtotal_usd"] for row in rows)
    by_arm = {}
    for arm in plan["arms"]:
        arm_rows = [row for row in rows if row["slot"]["arm"] == arm]
        by_arm[arm] = {"attempts": len(arm_rows), "scored": sum(row["scorable"] for row in arm_rows),
                       "reward_1": sum(row["verifier"]["reward"] == 1 for row in arm_rows),
                       "normal_unassisted_solved": sum(row["termination"] == "normal" and row["verifier"]["reward"] == 1 for row in arm_rows),
                       "termination": dict(Counter(row["termination"] for row in arm_rows)),
                       "runner_status": dict(Counter(row["runner_status"] for row in arm_rows)),
                       "infrastructure_failures": sum(row["runner_status"] == "infrastructure_failure" for row in arm_rows),
                       "infrastructure_failure_rate_per_attempt":
                           sum(row["runner_status"] == "infrastructure_failure" for row in arm_rows) / len(arm_rows) if arm_rows else None,
                       "estimated_cost_known_usd": sum(row["known_estimated_subtotal_usd"] for row in arm_rows),
                       "cost_incomplete_attempts": sum(row["total_estimated_usd"] is None for row in arm_rows)}
    return {"schema": 1, "planned_slots": len(slots), "scored_slots": len(complete),
            "attempted_slots": len({row["slot"]["slot_id"] for row in rows}),
            "infrastructure_failure_attempts": sum(row["runner_status"] == "infrastructure_failure" for row in rows),
            "infrastructure_failure_rate_per_attempt": sum(row["runner_status"] == "infrastructure_failure" for row in rows) / len(rows) if rows else None,
            "attempts": rows, "by_arm": by_arm, "paired": _paired(plan, rows),
            "known_estimated_cost_usd": known_cost,
            "cost_complete": all(value is not None for value in costs) and len(complete) == len(slots),
            "missing_cost_attempts": sum(value is None for value in costs),
            "limits": (["model aliases may drift"] if plan["model"]["floating_alias"] else [])
                      + ["an original-log file hash proves retention, while actual Agent readback requires a later Session tool result"]}
