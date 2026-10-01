"""Read only saved Pier, DSH Session, Jev ledger, and synthetic-fixture evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from bench.deepswe.config import FEATURES
from bench.deepswe.report import _model_usage, _search_usage, _usage_cost
from .cases import CASE_ORDER, cases


CONDITIONS = ("baseline", "file-ranking")
SCHEDULE = tuple((case, condition) for case in CASE_ORDER for condition in CONDITIONS)


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _content(message: dict) -> str:
    return "\n".join(item.get("text", "") for item in message.get("content", [])
                     if isinstance(item, dict) and item.get("type") == "text")


def _paths(text: str, case: str) -> list[str]:
    expression = rf"(?:\./)?src/jev-suite/{re.escape(case)}/[A-Za-z0-9_./-]+\.ts"
    return [match.removeprefix("./") for match in re.findall(expression, text)]


def _events(agent_dir: Path):
    files = list((agent_dir / "dsh-home" / "sessions").rglob("session.v4.jsonl"))
    if len(files) != 1:
        return None, None, "expected exactly one Session v4"
    try:
        rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line]
    except (OSError, ValueError):
        return None, None, "invalid Session JSONL"
    if not rows or rows[0].get("type") != "session" or rows[0].get("version") != 4:
        return None, None, "unsupported Session header"
    return rows[0].get("id"), rows[1:], None


def inspect_slot(root: Path, case: str, condition: str) -> dict:
    if case not in CASE_ORDER or condition not in CONDITIONS:
        raise ValueError("Unknown suite slot")
    plan = _json(root / "manifest.json")
    truth = _json(root / "cases" / case / "truth.json")
    expected = len(cases()[case]["files"])
    output = {"case": case, "condition": condition, "expected_candidates": expected,
              "status": "not-started", "blocking_errors": [], "semantic": None,
              "known_estimated_usd": None, "usage_complete": False}
    jobs = root / "jobs" / case / condition
    if not jobs.exists():
        return output
    output["status"] = "started"
    trials = list(jobs.glob("*/task__*/result.json"))
    if len(trials) != 1:
        output["blocking_errors"].append("Pier did not export exactly one completed trial result")
        return output
    trial = trials[0].parent
    result = _json(trials[0]) or {}
    job_result = _json(trial.parent / "result.json") or {}
    metadata = ((result.get("agent_result") or {}).get("metadata") or {})
    agent = trial / "agent"
    output.update({"status": "completed", "termination": metadata.get("termination"),
                   "dsh_exit_code": metadata.get("dsh_exit_code"),
                   "evidence_export": metadata.get("evidence_export"),
                   "fixture_integrity": (_json(agent / "fixture-integrity.json") or {}).get("status"),
                   "pier_exception": (result.get("exception_info") or {}).get("exception_type")})
    for key, wanted in (("termination", "normal"), ("dsh_exit_code", 0),
                        ("evidence_export", "complete"), ("fixture_integrity", "unchanged")):
        if output[key] != wanted:
            output["blocking_errors"].append(f"{key} differs from {wanted!r}")
    if output["pier_exception"] is not None:
        output["blocking_errors"].append("Pier trial has an exception")
    stats = job_result.get("stats") or {}
    if stats.get("n_completed_trials") != 1 or stats.get("n_errored_trials") != 0:
        output["blocking_errors"].append("Pier job did not finish exactly one trial without error")
    ready = _json(agent / "jev-service-ready.json") or {}
    features = ready.get("features") or {}
    expected_features = {name: condition == "file-ranking" and name == "file-ranking" for name in FEATURES}
    output["features_match"] = features == expected_features
    if not output["features_match"]:
        output["blocking_errors"].append("native feature marker differs from frozen condition")
    integrity = _json(agent / "fixture-integrity.json") or {}
    if integrity.get("expected_count") != expected or integrity.get("observed_count") != expected:
        output["blocking_errors"].append("fixture file count changed")

    session_id, events, session_error = _events(agent)
    if session_error:
        output["blocking_errors"].append(session_error)
        return output
    output["session_id"] = session_id
    types = Counter(event.get("type") for event in events)
    main = _model_usage(events, session_id, plan["prices"]["main"], plan["model"])
    search = _search_usage(events)
    output["main"] = main
    output["search"] = search
    if not main.get("complete") or main.get("calls", 0) < 1:
        output["blocking_errors"].append("main model usage is missing or no model call was recorded")
    if search.get("recorded_requests") != 0:
        output["blocking_errors"].append("auxiliary search request exists or search evidence is missing")
    endings = [(event.get("data") or {}).get("reason") for event in events if event.get("type") == "turn/end"]
    if len(endings) != 1 or (endings[0] or {}).get("kind") != "completed":
        output["blocking_errors"].append("Session lacks one normally completed turn")
    if (agent / "interactions.jsonl").exists() and (agent / "interactions.jsonl").stat().st_size:
        output["blocking_errors"].append("native human interaction was requested")

    calls: dict[str, tuple[str, dict]] = {}
    ordered_calls: list[str] = []
    tool_results: dict[str, list[dict]] = {}
    times: dict[str, int] = {}
    final_text = ""
    for event in events:
        kind = event.get("type")
        data = event.get("data") or {}
        if kind == "tool/call":
            try:
                args = json.loads(data.get("arguments") or "{}")
            except (ValueError, TypeError):
                args = {}
            name = data.get("name")
            calls[data.get("callId")] = (name, args)
            ordered_calls.append(name)
            times.setdefault(f"{name}_call", event.get("time"))
        elif kind == "tool/result":
            message = data.get("message") or {}
            name, args = calls.get(message.get("toolCallId"), (None, {}))
            tool_results.setdefault(name, []).append({"arguments": args,
                                                        "text": _content(message),
                                                        "is_error": message.get("isError")})
            times.setdefault(f"{name}_result", event.get("time"))
        elif kind == "assistant/message":
            text = _content(data.get("message") or {})
            if text:
                final_text = text
    output["tool_calls"] = ordered_calls
    if ordered_calls.count("grep") != 1 or ordered_calls.count("glob") != 1 or any(
        name not in ("grep", "glob", "read") for name in ordered_calls):
        output["blocking_errors"].append("tool calls differ from read-only grep/glob/read task")
    elif ordered_calls.index("grep") > ordered_calls.index("glob"):
        output["blocking_errors"].append("native grep did not precede glob")
    if any(value.get("is_error") for values in tool_results.values() for value in values):
        output["blocking_errors"].append("a native tool returned an error")
    if not tool_results.get("grep") or not tool_results.get("glob"):
        output["blocking_errors"].append("grep or glob result is missing")
        return output
    grep_paths = _paths(tool_results["grep"][0]["text"], case)
    glob_paths = _paths(tool_results["glob"][0]["text"], case)
    expected_paths = set((_json(root / "cases" / case / "fixture-expected.json") or {}).keys())
    output["grep_paths"] = grep_paths
    output["glob_visible_paths"] = glob_paths
    output["grep_match_count"] = len(grep_paths)
    if Counter(grep_paths) != Counter(expected_paths):
        output["blocking_errors"].append("grep match multiset differs from frozen fixture")
    if any(path not in expected_paths for path in glob_paths):
        output["blocking_errors"].append("glob output includes a non-fixture path")

    records = list((agent / "dsh-home" / "storages").glob("jev_*/operations/*.json"))
    invalid_records = sum(not isinstance(stored, dict) or not isinstance(stored.get("record"), dict)
                          for file in records for stored in [_json(file)])
    output["jev_record_files"] = len(records)
    output["jev_invalid_files"] = invalid_records
    eligible = condition == "file-ranking" and 0 < expected <= 40
    if not eligible:
        index = _json(agent / "original-logs" / "index.json")
        zero_proven = (metadata.get("termination") == "normal" and metadata.get("evidence_export") == "complete"
                       and (agent / "dsh-home" / "storages").is_dir() and index == []
                       and not list((agent / "dsh-home" / "storages").glob("jev_*")) and not records)
        if not zero_proven:
            output["blocking_errors"].append("zero Jev usage is not supported by a complete empty export")
        output["jev"] = {"operations": 0 if zero_proven else None,
                         "calls": 0 if zero_proven else None,
                         "estimated_usd": 0 if zero_proven else None, "complete": zero_proven}
        if len(glob_paths) != expected or set(glob_paths) != expected_paths:
            output["blocking_errors"].append("native bypass glob did not display the complete original candidate list")
        if re.search(r"Jev evaluated|relevance probability", tool_results["glob"][0]["text"]):
            output["blocking_errors"].append("bypass glob unexpectedly shows Jev ranking text")
        if list((agent / "spills").rglob("*-jev-glob-ranked.txt")):
            output["blocking_errors"].append("bypass glob unexpectedly wrote a Jev ranking spill")
        output["original_glob_paths"] = glob_paths
    else:
        if len(records) != 1 or invalid_records:
            output["blocking_errors"].append("eligible glob lacks one valid Jev operation")
        else:
            record = _json(records[0])["record"]
            attempts = record.get("attemptRecords") or []
            receipt = [(item.get("id"), item.get("status")) for item in record.get("receipts") or []]
            if record.get("featureId") != "file-ranking" or record.get("status") != "succeeded" \
                    or len(attempts) != 1 or attempts[0].get("status") != "succeeded" \
                    or ("glob-paths-ranked", "observed") not in receipt:
                output["blocking_errors"].append("Jev judgment or ranking adoption did not succeed")
            else:
                attempt = attempts[0]
                questions = (attempt.get("request") or {}).get("questions") or []
                answers = (attempt.get("response") or {}).get("answers") or []
                if len(questions) != expected or len(answers) != expected:
                    output["blocking_errors"].append("Jev request/answer count differs from candidates")
                original = []
                for index, (question, answer) in enumerate(zip(questions, answers)):
                    if question.get("id") != answer.get("id") or question.get("id") != f"candidate-{index}" \
                            or answer.get("kind") != "noul" or type(answer.get("probability")) not in (int, float):
                        output["blocking_errors"].append("Jev response id/type/probability is invalid")
                        break
                    prompt = question.get("prompt", "")
                    original.append({"path": prompt.rsplit("Path: ", 1)[-1].removeprefix("./"),
                                     "probability": answer["probability"], "original_index": index})
                original_paths = [item["path"] for item in original]
                if len(original_paths) != expected or set(original_paths) != expected_paths:
                    output["blocking_errors"].append("Jev request candidates differ from original glob fixture")
                sorted_paths = [item["path"] for item in sorted(original,
                               key=lambda item: (-item["probability"], item["original_index"]))]
                output["original_glob_paths"] = original_paths
                output["ranked_paths"] = sorted_paths
                output["scores"] = original
                output["ties"] = [{"probability": score,
                                   "original_indices": [item["original_index"] for item in original if item["probability"] == score]}
                                  for score in sorted({item["probability"] for item in original}, reverse=True)
                                  if sum(item["probability"] == score for item in original) > 1]
                if glob_paths != sorted_paths[:min(expected, 12)]:
                    output["blocking_errors"].append("model-visible glob paths differ from Jev score order")
                spill_files = list((agent / "spills").rglob("*-jev-glob-ranked.txt"))
                if expected > 12:
                    if len(spill_files) != 1:
                        output["blocking_errors"].append("complete ranked spill is missing")
                    else:
                        spill = spill_files[0]
                        full = _paths(spill.read_text(encoding="utf-8"), case)
                        output["spill_sha256"] = hashlib.sha256(spill.read_bytes()).hexdigest()
                        output["spill_paths"] = full
                        if full != sorted_paths:
                            output["blocking_errors"].append("spill does not contain every path in score order")
                        recovered = [item for item in tool_results.get("read", [])
                                     if item["arguments"].get("file_path", "").endswith(str(spill.relative_to(agent)))]
                        if len(recovered) != 1 or _paths(recovered[0]["text"], case) != sorted_paths:
                            output["blocking_errors"].append("Agent did not read back all ranked spill paths")
                elif spill_files:
                    output["blocking_errors"].append("in-cap ranking unexpectedly wrote a spill")
                started = record.get("startedAt")
                if not started or not times.get("grep_result") or not times.get("glob_call") or not times.get("glob_result"):
                    output["blocking_errors"].append("cannot order grep, glob, and Jev operation")
                else:
                    epoch = int(datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp() * 1000)
                    if not ("grep" in ordered_calls and "glob" in ordered_calls
                            and ordered_calls.index("grep") < ordered_calls.index("glob")
                            and times["grep_result"] <= epoch
                            and times["glob_call"] <= epoch <= times["glob_result"]):
                        output["blocking_errors"].append("Jev operation did not follow the grep control and glob call")
                usage = attempt.get("usage") if isinstance(attempt.get("usage"), dict) else {}
                jev = _usage_cost([usage], plan["prices"]["jev"], jev=True)
                output["jev"] = {"operations": 1, "status": record.get("status"),
                                 "attempt_status": attempt.get("status"), "response_model": (attempt.get("rawResponse") or {}).get("model"),
                                 "receipt": receipt, "latency_ms": attempt.get("latencyMs"), **jev}
                if not jev["complete"] or output["jev"]["response_model"] != plan["jev"]["model"]:
                    output["blocking_errors"].append("Jev usage is incomplete or response model differs from manifest")
    if "jev" not in output:
        output["jev"] = {"operations": None, "complete": False, "estimated_usd": None}

    targets = truth["targets"]
    positions = output.get("ranked_paths") or output.get("original_glob_paths") or []
    answer_suffixes = [target.removeprefix(f"src/jev-suite/{case}/") for target in targets]
    final_target_hits = {target: suffix in final_text for target, suffix in zip(targets, answer_suffixes)}
    final_fact_hits = {token: bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])", final_text))
                       if token.isdigit() else token in final_text for token in truth["fact_tokens"]}
    target_ranks = {target: positions.index(target) + 1 if target in positions else None for target in targets}
    read_targets = {target: any((item["arguments"].get("file_path") or "").removeprefix("./").endswith(target)
                                for item in tool_results.get("read", [])) for target in targets}
    output["semantic"] = {"targets": targets, "target_ranks": target_ranks,
                          "targets_in_final_answer": final_target_hits,
                          "targets_read_from_source": read_targets,
                          "fact_tokens_in_final_answer": final_fact_hits,
                          "top12_recall": (sum(rank is not None and rank <= 12 for rank in target_ranks.values()) / len(targets))
                          if targets and eligible else None,
                          "no_match_stated": bool(re.search(r"\b(no|none|not found|does not exist)\b", final_text, re.I))
                          if not targets else None}
    if main.get("estimated_usd") is not None and output["jev"].get("estimated_usd") is not None \
            and search.get("estimated_usd") is not None:
        output["known_estimated_usd"] = (main["estimated_usd"] + output["jev"]["estimated_usd"]
                                         + search["estimated_usd"])
        output["usage_complete"] = True
    else:
        output["blocking_errors"].append("cost usage is incomplete")
    output["structural_ok"] = not output["blocking_errors"]
    return output


def gate_before(root: Path, case: str, condition: str) -> None:
    index = SCHEDULE.index((case, condition))
    total = 0.0
    for previous_case, previous_condition in SCHEDULE[:index]:
        row = inspect_slot(root, previous_case, previous_condition)
        if row.get("status") != "completed" or not row.get("structural_ok") or not row.get("usage_complete"):
            raise RuntimeError(f"Earlier suite slot {previous_case}/{previous_condition} needs operator inspection")
        total += row["known_estimated_usd"]
    plan = _json(root / "manifest.json")
    if total >= plan["budget"]["max_batch_spend_usd"]:
        raise RuntimeError("Advisory suite cost threshold was reached before this trial")
    print(json.dumps({"previous_known_estimated_usd": round(total, 9),
                      "advisory_threshold_usd": plan["budget"]["max_batch_spend_usd"],
                      "next": [case, condition]}, sort_keys=True))


def report_batch(batch: Path, output: Path) -> dict:
    """Write one offline summary without altering frozen inputs or starting a model."""
    rows = [inspect_slot(batch, case, condition) for case, condition in SCHEDULE]
    value = {"schema": 1, "slots": rows, "planned_trials": len(SCHEDULE),
             "completed_trials": sum(row.get("status") == "completed" for row in rows),
             "structurally_valid_trials": sum(row.get("structural_ok") is True for row in rows),
             "known_estimated_usd": sum(row.get("known_estimated_usd") or 0 for row in rows),
             "missing_cost_trials": sum(row.get("status") != "not-started" and not row.get("usage_complete") for row in rows),
             "interpretation": "Synthetic single-run functional cases; no general path-ranking accuracy or DeepSWE benefit claim"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "completed_trials": value["completed_trials"],
                      "structurally_valid_trials": value["structurally_valid_trials"],
                      "missing_cost_trials": value["missing_cost_trials"],
                      "known_estimated_usd": value["known_estimated_usd"]}, sort_keys=True))
    return value
