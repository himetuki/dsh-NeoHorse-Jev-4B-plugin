# 原生 glob 文件路径排序验证

[English](README.md)

这套维护者测试验证 Jev 对**原生 `glob` 文件路径**的现有排序功能，不给 `grep` 新增排序、不为 DeepSWE 题目评分，也不改变插件。固定的六个人工案例分别有 0、1、12、16、40、41 个匹配路径；每例先运行关闭 file-ranking 的对照组，再运行仅开启 file-ranking 的实验组，各一次。0 和 41 路径验证产品不发起判断请求的旁路；1、12、16、40 路径可以各触发一次 Jev 排序请求。默认候选上限 40，展示上限 12。

管线复用 [DeepSWE 适配器](../deepswe/README.zh-CN.md)的固定 Docker 镜像、发布版 DSH 准备、原生凭据服务、Session/Jev 证据导出和文件完整性检查。清单中的 `vitest-duration-sharding` **只提供镜像和 bootstrap 标识**。六道题是本管线生成的人工文件定位题，verifier 已关闭。结构性功能检查与目标排名、主模型答案正确性分别报告。

## 准备并冻结输入

在新检出的仓库或隔离 worktree 中准备 Docker、`uv`、Node.js、pnpm、Python 3.12+，以及固定版本的 [DeepSWE](https://github.com/datacurve-ai/deep-swe) 和 [Pier](https://github.com/datacurve-ai/pier)。按照锁文件安装依赖，打包**仓库根包**；当前包须包含 `package/packages/jev/cordis.patch.yml` 和 `package/runtime/stage-navigation.js`。旧的 11 项功能子包会被拒绝。当前 profile 记录 12 个功能开关，其中 stage-navigation 关闭；不会把先前 11 项功能的[实测结果](../../docs/testing/2026-10-01-glob-ranking/README.md)写成新版重跑。

```sh
pnpm install --frozen-lockfile
pnpm run build
mkdir -p dist .artifacts/selection-suite
pnpm pack --pack-destination "$PWD/dist"
cp bench/selection/manifest.example.json .artifacts/selection-suite/manifest.json
```

运行 `prepare` 前须填完清单占位：DeepSWE、Pier、Linux Node 压缩包和根包的绝对路径，各自准确的提交和 SHA-256，seed 任务目录哈希、镜像 digest，以及注明日期与来源的主模型/Jev 非负单价。`bench.deepswe.config.digest` 和 `tree_digest` 可算文件与任务目录哈希。清单固定 DeepSeek Flash/high、Jev 1.13.0、Agent 120 秒、零自动重试、关闭 Agent 网页工具，以及**在默认权限隔离 Docker 容器内部**使用 `danger-full-access`。USD 1 是提示性估算阈值，不是服务商硬限额。清单只保存凭据引用名，绝不写密钥值。

在仓库根目录，将 `PIER` 设为固定 Pier checkout，`BATCH` 设为新的忽略目录：

```sh
uv run --project "$PIER" python -m bench.selection.cli prepare --manifest .artifacts/selection-suite/manifest.json --batch "$BATCH"
uv run --project "$PIER" python -m bench.selection.cli check --batch "$BATCH"
uv run --project "$PIER" python -m bench.selection.cli preflight --batch "$BATCH"
uv run --project "$PIER" python -m bench.selection.smoke.check --batch "$BATCH"
```

`prepare` 固定六套文件、只供宿主评价的真值、profile、12 槽顺序、bootstrap 依赖锁和源码/输入哈希，同时核查固定镜像与当前根包。`preflight` 用占位值构造全部 Pier Job/Trial 对象，不启动容器或调用模型。最后一条命令在隔离的**发布版 DSH 宿主 profile**安装同一包，加载两组条件，并在本地 mock 模型的首个请求停止；它保存完整工具 schema 哈希，核查两组工具目录相同、selection 已启用、stage-navigation 已禁用、无网页工具，且不调用服务商。宿主烟测**不能**证明 Docker 内执行或题目结果。源码、文件、profile、依赖锁或包改变时须另建**新批次**，保留旧批次证据。

## 逐槽运行并检查

固定顺序为 `zero`、`single`、`twelve`、`nested-sixteen`、`multi-forty`、`over-forty-one`，每例先 `baseline` 后 `file-ranking`。一次只运行一槽。launcher 通过发布版 DSH 原生凭据服务解析 `DEEPSEEK_API_KEY` 和 `JEV_API_KEY`，只在内存中供给该 trial，并从保存的 Pier 输出中过滤密钥值。若 Jev 只能另行供给，`--jev-key-stdin` 接受受保护的**非 TTY**管道输入一行；不得回显或落盘。管线没有 run-all、自动回答或自动付费重试。

```sh
node bench/selection/credential_launcher.mjs run --batch "$BATCH" --case zero --condition baseline --execute
uv run --project "$PIER" python -m bench.selection.cli inspect --batch "$BATCH" --case zero --condition baseline
```

进入下一槽前，检查正常结束、Session 用量、证据导出、Jev operation 和费用完整性。若先前槽缺结构性或用量证据，或已知估算额达到阈值，runner 会阻止继续。已开始但没有 Pier 结果的槽**费用未知**，不能补零。Pier 外层时限为准备和证据收集留出时间；Agent 自身固定时限仍是 120 秒。

全部结束后离线生成报告：

```sh
uv run --project "$PIER" python -m bench.selection.cli report --batch "$BATCH" --output "$BATCH/report.json"
```

分析器核对原生 `grep` 旁路、`glob` 候选数、一次请求或零请求、Jev 分数及同分稳定性、前 12 项展示、完整结果 spill 恢复、源码读取、文件哈希和用量；目标排名与最终答案提示另列。semantic 字段只做路径、关键词、数字 token 的**机械命中提示**，不是独立 verifier 或完整语义判定；操作者还需阅读保存的 Session 才能判断答案。[历史 12 槽报告](../../docs/testing/2026-10-01-glob-ranking/public-results.zh-CN.md)对其当时的冻结输入做了人工核查；本维护管线未在当前 12 项功能的包上重跑。
