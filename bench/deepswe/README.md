# DeepSWE paired evaluation

[简体中文](README.zh-CN.md)

This maintainer tool runs the same DeepSWE coding task through an isolated DSH Agent in each experimental arm. Pier owns the trial containers; the task's independent DeepSWE verifier scores the collected patch. The tool keeps the verifier result, Agent termination, Jev participation, and usage evidence separate. It does not change the plugin's normal behavior or the official tasks.

This directory provides a local evaluation runner. Earlier simulated DSH/Pier/verifier smoke covered both arms but is **not** evidence that the plugin improves coding outcomes. The first complete real DeepSeek pair, batch6, used one original task with `danger-full-access` and no Agent web tools. Both arms ended normally and independently passed reward 1, F2P 56/56, and P2P 24/24:

| Arm | Main-model calls | Agent time | Estimated main-model cost |
| --- | ---: | ---: | ---: |
| `baseline` | 150 | 610.249073 s | USD 0.221869176 |
| `log_admission` | 181 | 943.265423 s | USD 0.275539272 |

Both arms had zero search requests. The enabled arm's evidence export completed, with empty Jev storages and a parsed empty index, establishing **zero Jev records and calls rather than missing records**. The pair's known estimated cost is USD 0.497408448 at the recorded peak rates, not a provider invoice. This is **one task and one pair**: both passing and the observed time/cost differences do not establish a Jev benefit or regression, especially because Jev did not participate. See the [local-only batch6 report](../../.artifacts/real-pilot/batch6/report.zh-CN.md); ignored `.artifacts/` reports are not present in a published repository checkout.

Earlier conditions remain separate. Batch3's `workspace-write` baseline stopped at `needs-human` after its native sandbox backend failed; its verifier recorded reward 0, F2P 0/56, and P2P 24/24, and no log arm ran ([local report](../../.artifacts/real-pilot/batch3/report.zh-CN.md)). Batch4 used `danger-full-access` with the old web tools: all eight direct `web_fetch` results were errors, so answer-text retrieval is **not established**; 84 internal WebSearch request events lacked usage, making its original total-cost accounting incomplete. Its Agent stopped and verifier completed before the log arm started ([local stop record](../../.artifacts/real-pilot/batch4/operator-stop.json)). Batch5, the first no-web attempt, failed during `npm ci` with public-registry HTTP 503 responses before a Session, Agent, verifier, or model call. None of batches 3–5 supplies a comparable paired effect result.

## Experimental arms

Every arm installs the **same plugin archive** into a fresh DSH `0.1.7-rc.2` headless profile. The profile uses the same main model, task instruction, tools, permissions, resource limits, and the plugin's existing feature parameters. Only the feature switches differ:

| Arm | Enabled switches | Purpose |
| --- | --- | --- |
| `baseline` | None of the twelve | Reference condition. |
| `log_admission` | `output-admission`, `test-log-admission` | Test whether admitted command and test logs change task results and resource use. |
| `completion_check` | `completion-check` | Test whether a real supplemental attempt improves completion. Run as a separate comparison. |

A `pilot` manifest accepts only `baseline` and `log_admission`. Completion checks can be run in another declared phase; enabling all features together does not identify which one caused a difference. An enabled feature may never meet its trigger conditions on a particular task. Record that as zero participation, not as a successful intervention.

The dedicated profile disables the unrelated `jev-selection` and `jev-stage-navigation` Loader rows in **every** arm. This keeps the skill catalog and model-visible tool set aligned with the no-plugin baseline precheck; the installed archive and all twelve feature-switch values are still recorded. The profile also disables workspace approval, so no Jev arm gains a different approval path. The earlier batch6 used an eleven-feature archive; updating this profile to the current twelve-feature package does not rerun or reclassify that result.

For the strict paired comparison, **every declared arm** also disables the public `tool-web` Loader row, removing `web_search` and `web_fetch` from the Agent's tool catalog. The fixed tool-set identity is `dsh-headless-no-web-tools`; all other tool definitions must remain equal across arms. Record this as a new batch condition rather than merging results from the old default-tool batches. The outer setup may still use the declared inference and npm network access; disabling the Agent web tools does not change the official task or verifier.

## Prepare the environment

Run the commands below from this repository's isolated feature worktree. Keep DeepSWE and Pier in ignored `.artifacts/` directories or another dedicated location, outside tracked plugin source. Use Python 3.12 or later and `uv` for the pinned Pier project. The reference commits are [DeepSWE `0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea`](https://github.com/datacurve-ai/deep-swe/commit/0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea) and [Pier `4d3c14041d16443f3f9f460dcdf23629994a304e`](https://github.com/datacurve-ai/pier/commit/4d3c14041d16443f3f9f460dcdf23629994a304e). These are source references, not a claim that every task image and dependency has been reproduced locally.

1. Install and start Docker; verify `docker info` succeeds. Pier needs Docker access and the selected task image. Do not remove shared Docker networks or images to prepare a batch.
2. Clone DeepSWE and Pier, check out the commits above, and prepare the Pier project with `uv sync --project <pinned Pier checkout> --frozen`. This runner calls `uv run --project <pinned Pier checkout> pier run`; the adapter imports `pier` from that project environment. Follow [Pier's installation documentation](https://github.com/datacurve-ai/pier/blob/4d3c14041d16443f3f9f460dcdf23629994a304e/README.md#install) for its Docker requirements.
3. Build and pack this plugin once with `pnpm install --frozen-lockfile`, `pnpm run build`, and `pnpm -C packages/jev pack --pack-destination "$PWD/dist"` after creating `dist/`. Put the **absolute path** and SHA-256 of the resulting archive in the manifest. The runner installs that archive into a new trial profile; it does not read or alter an existing user profile. Keep Node.js and pnpm versions fixed. If task images lack the selected Node release, supply an absolute `node_tarball` path and checksum in the manifest.
4. Choose a fixed list of DeepSWE task IDs. Record why those tasks were selected **before** observing outcomes. The manifest includes each task directory checksum and image digest. The checker rejects changes to the task files, Git commits, or plugin archive. Check third-party task repositories and images under their own terms.
5. Set the main provider/model/route/reasoning setting and Jev endpoint/model explicitly. Supply two credential **reference names** through `conditions.main_credential_env` and `jev.credential_env`; these are also the environment variable names passed to isolated trials. Do not put secret values in the manifest, shell history, reports, or this repository. The runner does not read an existing DSH profile or private Session.

For the supported official DeepSeek route, use `model.provider: "deepseek-official"`, `model.id: "deepseek-flash"`, `model.route: "deepseek-official/deepseek-flash"`, `model.reasoning_effort: "high"`, and `model.endpoint: "https://api.deepseek.com/anthropic"`. The main model uses the `DEEPSEEK_API_KEY` reference in the example. Jev has its **own** endpoint, model, and credential reference; a configured DeepSeek key does not configure Jev. The sample manifest still contains invalid paths, hashes, prices, and budget placeholders and is not a runnable paid plan.

`versions.pnpm: "11.7.0"` pins the temporary DSH bootstrap CLI under `/tmp/jev-deepswe/cli`, where the adapter checks that version. It does not override a task repository's `packageManager`: the Vitest task selects `pnpm@10.31.0` in `/app`. Each trial records both `bootstrap_pnpm` and `task_pnpm`; do not change a task's package-manager version to match the bootstrap.

For fresh dependency checkouts in the ignored `.artifacts/` directory:

```sh
mkdir -p .artifacts dist
git clone https://github.com/datacurve-ai/deep-swe.git .artifacts/deep-swe-source
git -C .artifacts/deep-swe-source checkout 0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea
git clone https://github.com/datacurve-ai/pier.git .artifacts/pier-source
git -C .artifacts/pier-source checkout 4d3c14041d16443f3f9f460dcdf23629994a304e
uv sync --project .artifacts/pier-source --frozen
pnpm install --frozen-lockfile
pnpm run build
pnpm -C packages/jev pack --pack-destination "$PWD/dist"
```

Use the actual archive produced by the final command. Check its SHA-256, the task directory tree hashes, and the selected image digests when filling the manifest; the runner verifies them again before execution. A `check` result alone does not establish that the pinned image can be pulled or that the container's DSH hooks work.

The checker uses these hash functions; substitute your absolute paths:

```sh
python3 -c 'from pathlib import Path; from bench.deepswe.config import digest, tree_digest; print(digest(Path("/absolute/path/plugin.tgz"))); print(tree_digest(Path("/absolute/path/deep-swe/tasks/TASK_ID")))'
```

The manifest is a schema-1 JSON object. Its top-level fields are `schema`, `phase`, `selection_rule`, `paths`, `versions`, `tasks`, `arms`, `repeats`, `model`, `jev`, `conditions`, `budget`, and `prices`. Use [the example manifest](manifest.example.json) as a field guide, then review the model route and replace every example path, hash, task, Jev model, credential name, price source, context window, and budget with values for **your** batch. Its deliberately invalid zero and negative placeholders make `check` fail until a real plan is supplied. Each task also needs its Docker platform. `check` validates those values without starting an Agent or pulling an image. `run` pulls the pinned image digest for the selected platform before launching its trial. A floating provider alias must be marked with `model.floating_alias`; recording a local commit cannot freeze a remote model implementation.

The runner supports one trial at a time. The manifest must explicitly select `conditions.sandbox` as `workspace-write` or, for a separately authorized batch, `danger-full-access`; both arms use the same mode. Unknown modes are rejected, and a failed permission check never silently switches modes. `danger-full-access` removes DSH sandbox restrictions **inside the isolated task Docker container**; Docker still uses its default non-privileged settings, with no added capabilities, seccomp change, or host mounts. The planned order rotates arms across task/repeat slots before results are known. Agent and verifier timeouts are required. The explicit `budget.max_batch_spend_usd` is **advisory**: provider usage can arrive late, in-flight calls can incur charges, and this path cannot enforce a hard dollar cap. A manifest requesting `hard_usd_cap` is rejected. Set `budget.usage_incomplete_policy` to `halt` or `continue-with-unknown`, and do not use an advisory estimate as a purchasing guarantee.

This version enforces time limits and finite task/repeat counts; it does not enforce a per-turn step or token cap. Record those limits as unset rather than implying that the spend estimate controls them. Before a paid batch, use a controlled no-plugin versus installed-but-all-off run to check that the baseline adds no Jev request or model-visible content. That comparison is an integration gate, not a fourth outcome arm.

Before any real-model Agent setup, the declared permission mode must pass a preflight execution check. For `workspace-write`, `sandbox_precheck.mjs` uses the published DSH `LocalSandboxProvider` to confine `/usr/bin/true` in the task root, requires `enforcement: "full"`, and executes the confined command. For the explicitly authorized `danger-full-access` mode, the check must confirm that an unrestricted DSH command can execute inside the same isolated container; it must not add Docker privileges. A failed check stops setup before a model request. In the fixed Vitest image under default permissions, the `workspace-write` gate was verified to reject setup before credentials or model calls, exiting 2 with a `SANDBOX_UNAVAILABLE` marker. An isolated probe with only `SYS_ADMIN` added, Docker's default seccomp, no network, and no host mounts or credentials failed with `bwrap: pivot_root: Operation not permitted`; its disposable container was removed. See the [local-only sandbox audit](../../.artifacts/sandbox-probe/audit-2026-09-30.json). That image does not satisfy `workspace-write`; the separately authorized `danger-full-access` comparison requires a new manifest and batch. The earlier batch3 result remains its own condition and provides no real A/B conclusion.

For a non-paid container integration check, `phase: "smoke"` can use a local `model.fixture_module` and its `model.fixture_sha256`. Any enabled Jev arm also needs an explicitly local, deterministic Jev endpoint; the main-model fixture does **not** replace the Jev service. The fixture is excluded from `pilot` and `formal` manifests. A successful fixture trial proves only the configured DSH/Pier/verifier path and observed hooks, not paid-model behavior or benchmark benefit.

## Check, run, recover, and report

Run these commands from the worktree root with Python 3.12 or later; the CLI launches pinned Pier through `uv` for Docker trials. Replace `PLAN.json`, `BATCH_DIR`, `SLOT_ID`, and `N` with your actual manifest, new batch directory, slot ID, and attempt number. Inspect `python3 -m bench.deepswe.cli --help` before a real run. The first `run` freezes a new batch; `resume` reads its frozen manifest.

```sh
python3 -m bench.deepswe.cli check --manifest PLAN.json
node bench/deepswe/credential_launcher.mjs run --manifest PLAN.json --batch BATCH_DIR --execute
node bench/deepswe/credential_launcher.mjs resume --batch BATCH_DIR --execute
node bench/deepswe/credential_launcher.mjs resume --batch BATCH_DIR --execute --retry-interrupted
python3 -m bench.deepswe.cli reverify --batch BATCH_DIR --slot SLOT_ID --attempt N --execute
python3 -m bench.deepswe.cli report --batch BATCH_DIR --output REPORT.json
```

By default, the credential launcher resolves both declared references through DSH's normal local credential service and supplies their values only in the isolated child process environment. It uses DSH's launch environment and local credential provider; it does not open a user profile or private Session. If either required reference is unavailable, it stops before Pier starts. If dedicated values are already present in the execution environment, the direct `python3 -m bench.deepswe.cli run/resume ... --execute` commands also work. Neither route writes credential values into the manifest.

When the main DeepSeek reference is configured but the Jev key must come from a separate source, append `--jev-key-stdin` to the launcher `run` or `resume` command. This option requires `jev.credential_env: "JEV_API_KEY"`; it resolves the main reference normally and reads one Jev key line from standard input for the child environment. Supply that line from a controlled source that does not echo or log it. The launcher does not disable terminal echo, so typing a key directly into an ordinary terminal may display it. Never place a key in command arguments, the manifest, or a checked-in file.

`check` and `report` do not call either model. `run` and `resume` can start chargeable Agent trials and require `--execute`. The first run freezes the manifest and schedule in the batch directory. `resume` uses that frozen batch: it does not overwrite completed successes or task failures. The `--retry-interrupted` form is only for an inspected interrupted or infrastructure-failed slot with remaining declared retry allowance. Confirm that its earlier Pier process has stopped before using this option. `reverify` starts a fresh Pier verifier trial using an already saved patch; it does not rerun the main model, but it does use Docker and may need to prepare an image. Keep its output beside the original attempt rather than replacing it.

The first real `pilot` compares `baseline` and `log_admission` only. A small three-task, two-repeat pilot is a useful integration check, not a statistical claim. The task IDs, model route, provider limits, and advisory spend threshold must be chosen for the batch; this tool supplies no paid-run defaults or hard USD cap.

## Read the evidence

Keep the batch directory private. It contains the frozen plan and schedule; per-attempt Pier results, Agent stdout/stderr, profile configuration, DSH Session, Jev ledger, collected patch, verifier reward and test output; and offline reports. Raw Sessions, prompts, tool output, and error files may contain repository data or sensitive text. Review and redact before any publication. Runtime artifacts should not be committed with plugin source.

The report keeps each actual attempt, including failures and retries. Compare arms by task ID, task checksum, and repeat index; first summarize repeats within a task, then pair tasks. Do not select the latest or best attempt, and do not count repeated runs of one task as independent new tasks. A missing verifier result, Session, ledger, or usage field means **unknown or incomplete**, not zero. Explicit recorded zero is different. Estimated cost uses the manifest's cited prices and available request usage; it is not a provider invoice. Main-model and Jev usage remain separate, including recorded failed attempts. If a tool starts additional model requests without usage, report their observed count and unknown cost separately; main-model plus Jev estimates cannot be labeled complete total cost, as batch4 demonstrates.

The official `reward=1` says the independent verifier passed its defined tests. The report separately states whether the Agent finished normally without asking for a human; a timed-out attempt can still have a passing patch. F2P and P2P counts and raw verifier output remain authoritative for test behavior. A zero test count alone does not establish an infrastructure fault. Jev ledger calls alone do not show that a reduced log reached the model or that a requested completion supplement executed. The report marks participation that the available records cannot establish as unobservable.

An actual native question or Retry/Cancel request is recorded as `needs-human` and stops the unattended trial; final answer text that merely asks a question stays ordinary output for the verifier to score. The runner does not answer the Agent or approve native escalation. If the fixed headless profile cannot expose the required interaction or completion lifecycle, stop at integration validation instead of treating absent events as plugin inactivity.

## Limits and upstream material

This first integration covers the three declared arms under one DSH version and the supported DeepSWE/Pier formats. It does not assess Goal supervision, multi-Agent corrections, interjection routing, workspace approval, general patch quality, or whether a Jev judgment is semantically right in every case. Provider-side model aliases and caches can drift even when local inputs are pinned; record the run time and arm order. Re-scoring an existing patch tests verifier repeatability, not Agent repeatability.

The adapter is project code informed by the public [DeepSWE task format](https://github.com/datacurve-ai/deep-swe/blob/0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea/README.md) and [Pier execution API](https://github.com/datacurve-ai/pier/blob/4d3c14041d16443f3f9f460dcdf23629994a304e/README.md). Consult their Apache-2.0 licenses and the separate licenses of task repositories and container images before distributing copied materials. Do not mount reference patches, hidden verifier tests, previous results, or another arm's patch into the Agent environment.
