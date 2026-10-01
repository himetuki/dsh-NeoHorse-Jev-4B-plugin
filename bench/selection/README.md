# Native glob file-ranking check

[简体中文](README.zh-CN.md)

This maintainer suite tests the existing Jev ranking of **native `glob` file paths**. It does not add ranking to `grep`, score a DeepSWE task, or change the plugin. Six fixed synthetic cases have 0, 1, 12, 16, 40, and 41 matching paths. Each runs once with file-ranking off and once with only file-ranking on, in that order. The 0- and 41-path cases exercise the product's no-request bypass; the 1-, 12-, 16-, and 40-path cases can send one Jev ranking request. The normal candidate limit is 40 and the displayed result limit is 12.

The suite reuses the [DeepSWE adapter](../deepswe/README.md) for a pinned Docker image, published DSH setup, the native credential service, Session and Jev evidence export, and fixture integrity. The declared `vitest-duration-sharding` task is **only an image and bootstrap seed**. The six tasks here are generated synthetic file-location questions; their verifier is disabled. A structural check is distinct from whether a target ranks highly or the main model answers correctly.

## Prepare and freeze

Use a fresh clone or isolated worktree with Docker, `uv`, Node.js, pnpm, Python 3.12+, pinned [DeepSWE](https://github.com/datacurve-ai/deep-swe) and [Pier](https://github.com/datacurve-ai/pier) checkouts. Install this repository's frozen lock and pack the **root** package; the current archive must contain `package/packages/jev/cordis.patch.yml` and `package/runtime/stage-navigation.js`. The older eleven-feature subpackage archive is intentionally rejected. The current profile records twelve feature switches, including stage-navigation off. It does not recast the earlier eleven-feature [observed run](../../docs/testing/2026-10-01-glob-ranking/README.md) as a new run.

```sh
pnpm install --frozen-lockfile
pnpm run build
mkdir -p dist .artifacts/selection-suite
pnpm pack --pack-destination "$PWD/dist"
cp bench/selection/manifest.example.json .artifacts/selection-suite/manifest.json
```

Fill every placeholder in the copied manifest before running `prepare`: absolute DeepSWE, Pier, Node Linux tarball and root package archive paths; their exact commits and SHA-256 digests; the seed task tree digest and image digest; and dated main/Jev price sources and nonnegative rates. `bench.deepswe.config.digest` and `tree_digest` calculate file and task-tree hashes. The manifest declares DeepSeek Flash/high, Jev 1.13.0, 120 seconds per Agent, no automatic retries, no Agent web tools, and `danger-full-access` **inside the isolated default-permission Docker container**. Its USD 1 threshold is an advisory estimate, not a provider hard cap. It contains credential reference names only. Never put key values in the manifest or shell command.

From the repository root, with `PIER` set to your pinned Pier checkout and `BATCH` to a new ignored directory:

```sh
uv run --project "$PIER" python -m bench.selection.cli prepare --manifest .artifacts/selection-suite/manifest.json --batch "$BATCH"
uv run --project "$PIER" python -m bench.selection.cli check --batch "$BATCH"
uv run --project "$PIER" python -m bench.selection.cli preflight --batch "$BATCH"
uv run --project "$PIER" python -m bench.selection.smoke.check --batch "$BATCH"
```

`prepare` fixes the six fixtures, host-only truth, profiles, 12-slot schedule, package-lock bootstrap and source/input hashes. It checks the pinned image and current root archive. `preflight` constructs all Pier Job/Trial objects with placeholders without starting a container or calling a model. The final command installs that same archive into an isolated **published DSH host profile**, loads both conditions, and stops each at a local mock model's first request. It records their full tool-schema hashes and verifies equal catalogs, enabled selection, disabled stage-navigation, and no web tools. It makes no provider call. This host smoke does **not** establish Docker execution or task outcomes. A changed source, fixture, profile, dependency lock, or package archive requires a **new batch**. Keep earlier batch files intact.

## Run one slot, inspect, then decide

The fixed order is `zero`, `single`, `twelve`, `nested-sixteen`, `multi-forty`, `over-forty-one`, with `baseline` then `file-ranking` within each case. Run one slot at a time. The launcher resolves `DEEPSEEK_API_KEY` and `JEV_API_KEY` through published DSH local credentials, passes them in memory to that trial, and redacts their values from captured Pier output. If Jev exists only as a separately supplied key, `--jev-key-stdin` accepts one line from a protected **non-TTY** pipe; never echo or save it. There is no run-all, auto-answer, or automatic paid retry.

```sh
node bench/selection/credential_launcher.mjs run --batch "$BATCH" --case zero --condition baseline --execute
uv run --project "$PIER" python -m bench.selection.cli inspect --batch "$BATCH" --case zero --condition baseline
```

Inspect normal termination, Session usage, evidence export, Jev operation and cost completeness before the next slot. The runner blocks the next slot if an earlier slot lacks structural or usage evidence or if the known estimate reaches the declared threshold. A started slot with no Pier result has **unknown cost**, not zero. The outer Pier timeout allows setup and evidence collection; the Agent's own declared limit remains 120 seconds.

After the schedule, create an offline report:

```sh
uv run --project "$PIER" python -m bench.selection.cli report --batch "$BATCH" --output "$BATCH/report.json"
```

The analyzer checks the native `grep` bypass, `glob` candidate count, one-request/zero-request cases, Jev scores and stable ties, top-12 display, full-result spill recovery, source reads, fixture hashes, and recorded usage. It reports target ranks and final-answer hints separately from structural behavior. Its semantic fields use path, keyword, and numeric-token matches only; they are **mechanical hints**, not an independent verifier or complete semantic judgment. An operator must read the saved Session to judge the answer. The [historical 12-slot report](../../docs/testing/2026-10-01-glob-ranking/public-results.zh-CN.md) includes that manual check for its own frozen inputs; this maintained pipeline has not been rerun on the current twelve-feature archive.
