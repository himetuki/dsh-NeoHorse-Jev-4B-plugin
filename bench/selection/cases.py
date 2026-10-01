"""Frozen, synthetic path-only tasks for the existing glob-ranking feature."""

from __future__ import annotations


CASE_ORDER = ("zero", "single", "twelve", "nested-sixteen", "multi-forty", "over-forty-one")
MARKER = "SELECTION_SUITE_TOKEN"


def _file(name: str, body: str = "export const placeholder = true;\n") -> tuple[str, str]:
    return name, f"export const {MARKER} = true;\n" + body


def cases() -> dict[str, dict]:
    twelve_names = [
        "01-date-format.ts", "02-path-normalize.ts", "03-color-theme.ts", "04-url-parse.ts",
        "05-cache-key.ts", "06-request-header.ts", "07-log-level.ts", "08-metrics.ts",
        "09-json-schema.ts", "10-state-render.ts", "11-queue-length.ts",
    ]
    nested_names = [
        "parser/token/refresh.ts", "cache/token/refresh.ts", "ui/session/refresh.ts",
        "auth/session/refresh.ts", "parser/token/parse.ts", "cache/token/evict.ts",
        "ui/session/display.ts", "auth/session/expire.ts", "auth/session/revoke.ts",
        "http/client.ts", "http/header.ts", "logging/events.ts", "metrics/count.ts",
        "storage/index.ts", "storage/ttl.ts", "types/session.ts",
    ]
    forty_names = [
        "auth/session/refresh-access-token.ts", "auth/session/token-store.ts",
        "parser/token/refresh-access-token.ts", "auth/schema/token-store.ts",
        "auth/ui/token-store.ts",
        *[f"module-{i:02d}/adapter.ts" for i in range(1, 36)],
    ]
    forty_one_names = [
        "security/lease-expiration.ts",
        *[f"module-{i:02d}/feature.ts" for i in range(1, 41)],
    ]
    result = {
        "zero": {
            "files": {},
            "question": "Is there an implementation of the removed legacy fax protocol in this directory? If none exists, say so clearly.",
            "truth": {"targets": [], "answer_facts": ["no matching file"], "fact_tokens": []},
        },
        "single": {
            "files": dict([_file("auth/access-token-refresh.ts",
                "export const MAX_REFRESH_ATTEMPTS = 2;\n"
                "export function refreshExpiredAccessToken(attempt: number): boolean { return attempt < MAX_REFRESH_ATTEMPTS; }\n")]),
            "question": "Locate the expired access-token refresh retry policy. Read it and report the path and maximum attempt count.",
            "truth": {"targets": ["auth/access-token-refresh.ts"], "answer_facts": ["MAX_REFRESH_ATTEMPTS = 2"], "fact_tokens": ["2"]},
        },
        "twelve": {
            "files": dict([*[_file(name) for name in twelve_names],
                _file("12-circuit-reset.ts",
                    "export const CIRCUIT_RESET_WINDOW_MS = 4500;\n"
                    "export function mayResetCircuit(elapsedMs: number): boolean { return elapsedMs >= CIRCUIT_RESET_WINDOW_MS; }\n")]),
            "question": "Locate the upstream HTTP circuit-breaker reset cooldown. Read the implementation and report the path and reset window in milliseconds.",
            "truth": {"targets": ["12-circuit-reset.ts"], "answer_facts": ["CIRCUIT_RESET_WINDOW_MS = 4500"], "fact_tokens": ["4500"]},
        },
        "nested-sixteen": {
            "files": dict(_file(name,
                "export const MAX_OAUTH_REFRESH_ATTEMPTS = 4;\n"
                "export function renewExpiredOAuthAccessToken(attempt: number): boolean { return attempt < MAX_OAUTH_REFRESH_ATTEMPTS; }\n"
                if name == "auth/session/refresh.ts" else
                "export function refresh(): string { return 'unrelated local state'; }\n")
                for name in nested_names),
            "question": "Among same-named files in different directories, locate the OAuth access-token renewal attempt-limit policy. Read it and report its path and maximum attempts.",
            "truth": {"targets": ["auth/session/refresh.ts"], "answer_facts": ["MAX_OAUTH_REFRESH_ATTEMPTS = 4"], "fact_tokens": ["4"]},
        },
        "multi-forty": {
            "files": dict(_file(name,
                "export const MAX_ROTATION_ATTEMPTS = 3;\n"
                "export function requestRotatedAccessToken(attempt: number): boolean { return attempt < MAX_ROTATION_ATTEMPTS; }\n"
                if name == "auth/session/refresh-access-token.ts" else
                "export const ROTATED_TOKEN_STORAGE_KEY = 'active-access-token';\n"
                "export function persistRotatedToken(token: string): string { return ROTATED_TOKEN_STORAGE_KEY + token; }\n"
                if name == "auth/session/token-store.ts" else
                "export function parseLexicalToken(value: string): string { return value; }\n"
                if name == "parser/token/refresh-access-token.ts" else
                "export const placeholder = true;\n")
                for name in forty_names),
            "question": "Find the source files that define the API access-token rotation retry limit and persistence key after HTTP 401. Read both, then report both paths, the maximum rotation attempts, and the persistence key.",
            "truth": {"targets": ["auth/session/refresh-access-token.ts", "auth/session/token-store.ts"],
                      "answer_facts": ["MAX_ROTATION_ATTEMPTS = 3", "ROTATED_TOKEN_STORAGE_KEY = active-access-token"],
                      "fact_tokens": ["3", "active-access-token"]},
        },
        "over-forty-one": {
            "files": dict(_file(name,
                "export const SECURITY_LEASE_TTL_SECONDS = 900;\n"
                "export function expiresAt(issuedAt: number): number { return issuedAt + SECURITY_LEASE_TTL_SECONDS; }\n"
                if name == "security/lease-expiration.ts" else
                "export const placeholder = true;\n")
                for name in forty_one_names),
            "question": "Locate the security lease expiration calculation. Read it and report the path and TTL in seconds.",
            "truth": {"targets": ["security/lease-expiration.ts"], "answer_facts": ["SECURITY_LEASE_TTL_SECONDS = 900"], "fact_tokens": ["900"]},
        },
    }
    assert [len(result[name]["files"]) for name in CASE_ORDER] == [0, 1, 12, 16, 40, 41]
    return result
