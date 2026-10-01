"""Generate equal DSH profile rows for every experimental arm."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DSH_VERSION, NO_WEB_TOOLSET, OUTPUT_DEFAULTS, feature_settings, validate_arm_settings


def patch_rows(plan: dict[str, Any], arm: str, *, guard_path: str | None = None,
               model_module_path: str | None = None) -> list[dict[str, Any]]:
    """Build a complete switch row while keeping all other rows equal."""
    features = feature_settings(arm)
    validate_arm_settings(arm, features)
    rows: list[dict[str, Any]] = [
        {"id": "agent-default-model", "config": {
            "provider": plan["model"]["provider"], "model": plan["model"]["id"],
            "reasoningEffort": plan["model"]["reasoning_effort"],
        }},
        {"id": "jev", "config": {
            "baseUrl": plan["jev"]["endpoint"], "model": plan["jev"]["model"],
            "credentialRef": plan["jev"]["credential_env"], "timeoutMs": 10000,
            "features": features,
        }},
        {"id": "jev-output-admission", "config": OUTPUT_DEFAULTS},
        # This unrelated row always registers skill_catalog even with its two
        # switches off; excluding it equally from all arms keeps baseline's
        # model-visible tool set identical to the no-plugin precheck.
        {"id": "jev-selection", "disabled": True},
        {"id": "jev-stage-navigation", "disabled": True},
        {"id": "session-persistence-jsonl", "config": {
            "root": "/logs/agent/dsh-home/sessions", "compression": "none",
        }},
        # The product must never answer native approvals in an evaluation trial.
        {"id": "jev-workspace-approval", "disabled": True},
        {"id": "session-title-llm", "disabled": True},
    ]
    if plan["conditions"]["toolset"] == NO_WEB_TOOLSET:
        rows.append({"id": "tool-web", "disabled": True})
    if plan["model"]["provider"] == "deepseek-official":
        rows.append({"id": "llm-deepseek", "config": {
            "baseURL": plan["model"]["endpoint"],
            "apiKeyEnv": plan["conditions"]["main_credential_env"],
            "reasoningEffort": plan["model"]["reasoning_effort"],
        }})
    if guard_path is not None:
        rows.append({"insert": [{"id": "eval-interaction-guard", "name": guard_path}]})
    if model_module_path is not None:
        rows.append({"insert": [{"id": "eval-mock-model", "name": model_module_path}]})
    return rows


def write_patch(path: Path, plan: dict[str, Any], arm: str, *, guard_path: str | None = None,
                model_module_path: str | None = None) -> None:
    path.write_text(json.dumps(patch_rows(plan, arm, guard_path=guard_path,
                                          model_module_path=model_module_path), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_published_dsh(version: str) -> None:
    if version != DSH_VERSION:
        raise ValueError(f"Profile requires published DSH {DSH_VERSION}")
