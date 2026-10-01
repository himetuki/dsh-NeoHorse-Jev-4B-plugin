# DeepSWE 配对评测

[English](README.md)

这套维护者工具让同一道 DeepSWE 编码任务分别交给隔离的 DSH Agent 实验组执行。Pier 管理 trial 容器；DeepSWE 的独立 verifier 为收集的补丁评分。工具分别保留测试结果、Agent 终止原因、Jev 实际参与情况和用量证据，不改变插件日常行为或官方题目。

这里提供的是本地评测入口。此前的模拟模型 DSH/Pier/verifier smoke 覆盖了两个组别，但**不能**据此推断插件提高了编码任务成功率。首个完成的真实 DeepSeek 配对 batch6 使用一道原始题目、`danger-full-access` 和不含 Agent 网页工具的条件。两组都正常结束，独立 verifier 均给出 reward 1、F2P 56/56、P2P 24/24：

| 组别 | 主模型调用 | Agent 耗时 | 主模型估算费用 |
| --- | ---: | ---: | ---: |
| `baseline` | 150 | 610.249073 秒 | USD 0.221869176 |
| `log_admission` | 181 | 943.265423 秒 | USD 0.275539272 |

两组搜索请求均为 0。启用组的证据导出完成、Jev storages 为空且索引成功解析为空列表，因此**Jev 记录和调用确实为 0，并非记录缺失**。本对按记录的峰时单价估算费用合计 USD 0.497408448，并非服务商账单。这里**只有一道题、一个配对**：两组都通过以及耗时、费用差异不能证明 Jev 有收益或退化，尤其本次 Jev 根本没有参与。详见[仅本地保存的 batch6 报告](../../.artifacts/real-pilot/batch6/report.zh-CN.md)；被忽略的 `.artifacts/` 报告不在公开仓库 checkout 中。

此前条件分别保留。batch3 的 `workspace-write` baseline 因原生沙箱后端不可用而以 `needs-human` 停止；独立 verifier 得到 reward 0、F2P 0/56、P2P 24/24，日志组未运行（[本地报告](../../.artifacts/real-pilot/batch3/report.zh-CN.md)）。batch4 使用 `danger-full-access` 和旧的网页工具：8 次直接 `web_fetch` 全报错，**不能证明已取回答案正文**；84 个 WebSearch 内部请求事件缺少 usage，原报告的总费用统计不完整。其 Agent 停止，verifier 完成后日志组未启动（[本地停止记录](../../.artifacts/real-pilot/batch4/operator-stop.json)）。首次无网页工具的 batch5 在 `npm ci` 阶段遭遇公开 registry 的 HTTP 503，未创建 Session，也未启动 Agent、verifier 或模型调用。batch3–5 都没有可比较的配对效果结果。

## 实验组

每组都把**同一份插件包**安装到新的 DSH `0.1.7-rc.2` headless profile。主模型、题目指令、工具、权限、资源限制和插件现有功能参数保持一致；只有开关不同：

| 组别 | 启用的开关 | 用途 |
| --- | --- | --- |
| `baseline` | 12 项全部关闭 | 对照条件。 |
| `log_admission` | `output-admission`、`test-log-admission` | 观察筛选后的命令和测试日志是否改变任务结果与资源消耗。 |
| `completion_check` | 仅 `completion-check` | 观察真实补做是否改善完成情况；单独比较。 |

`pilot` 清单只接受 `baseline` 与 `log_admission`。完成核查可在另一个声明的阶段运行；把全部功能一起打开，无法辨认是哪一项造成差异。开关已打开也不代表每题满足触发条件。未触发须记为零参与，不能写成成功干预。

专用 profile 在**每个**组别都禁用不参与本轮的 `jev-selection` 和 `jev-stage-navigation` Loader 行，使技能目录和模型可见工具集与未安装插件的 baseline 预检保持一致；安装包和全部 12 项功能开关值仍分别记录。profile 同样禁用工作区代审批，避免组间出现不同的审批路径。此前 batch6 使用的是 11 项功能的旧插件包；将当前 profile 更新为 12 项，不等于重跑或重新归类该结果。

严格配对时，**全部声明的组别**还统一禁用公开的 `tool-web` Loader 行，从 Agent 工具目录移除 `web_search` 与 `web_fetch`。固定工具集标识为 `dsh-headless-no-web-tools`；其他工具定义在组间仍须一致。这是新批次条件，不与旧的默认工具批次合并。外层准备阶段仍可按清单使用模型推理和 npm 所需网络；禁用 Agent 网页工具不改变官方题目或 verifier。

## 准备环境

在本仓库的隔离功能 worktree 中运行下列命令。把 DeepSWE 与 Pier checkout 放在被忽略的 `.artifacts/` 目录或其他专用位置，不纳入受版本控制的插件源码；固定的 Pier 项目需要 Python 3.12 或更新版本和 `uv`。参考提交为 [DeepSWE `0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea`](https://github.com/datacurve-ai/deep-swe/commit/0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea) 和 [Pier `4d3c14041d16443f3f9f460dcdf23629994a304e`](https://github.com/datacurve-ai/pier/commit/4d3c14041d16443f3f9f460dcdf23629994a304e)。它们是源码参考版本，不表示全部任务镜像与依赖都已在本机复现。

1. 安装并启动 Docker，确认 `docker info` 成功。Pier 需要访问 Docker 和所选任务的镜像。准备批次时不要删除共享的 Docker 网络或镜像。
2. Clone DeepSWE 与 Pier，并检出上面的提交，然后用 `uv sync --project <固定的 Pier checkout> --frozen` 准备 Pier 项目。runner 用 `uv run --project <固定的 Pier checkout> pier run` 执行，适配器从该项目环境导入 `pier`。Docker 要求遵循 [Pier 安装说明](https://github.com/datacurve-ai/pier/blob/4d3c14041d16443f3f9f460dcdf23629994a304e/README.md#install)。
3. 在创建 `dist/` 后，依次使用 `pnpm install --frozen-lockfile`、`pnpm run build`、`pnpm -C packages/jev pack --pack-destination "$PWD/dist"` 构建并打包一次，在清单中填入包的**绝对路径**和 SHA-256。runner 把它安装到新的 trial profile，不读取或修改已有用户 profile。固定 Node.js 与 pnpm 版本。若任务镜像没有选定的 Node 版本，在清单里给出 `node_tarball` 的绝对路径及校验和。
4. 固定 DeepSWE 任务 ID 清单，在看到结果**之前**记录选题理由。清单包含每题目录校验和与镜像 digest。检查入口会拒绝任务文件、Git 提交或插件包发生变化的批次。第三方题目仓库和镜像还需按其各自条款使用。
5. 明确填写主模型 provider/model/route/推理设置和 Jev endpoint/model。通过 `conditions.main_credential_env` 与 `jev.credential_env` 指定两个**凭据引用名**；它们也是传入隔离 trial 的环境变量名。密钥值不要放进清单、shell 历史、报告或仓库。runner 不读取已有 DSH profile 或私人 Session。

当前支持的 DeepSeek 官方路由使用 `model.provider: "deepseek-official"`、`model.id: "deepseek-flash"`、`model.route: "deepseek-official/deepseek-flash"`、`model.reasoning_effort: "high"`，以及 `model.endpoint: "https://api.deepseek.com/anthropic"`。示例中主模型使用 `DEEPSEEK_API_KEY` 引用。Jev 有**独立的**服务地址、模型和凭据引用；DeepSeek 凭据已配置不代表 Jev 也已配置。示例清单仍含无效路径、哈希、价格和预算占位，不能直接用于付费运行。

`versions.pnpm: "11.7.0"` 固定的是 `/tmp/jev-deepswe/cli` 中临时 DSH bootstrap CLI 的 pnpm，适配器会核对该版本；它不会覆盖题目仓库的 `packageManager`。Vitest 题在 `/app` 选用 `pnpm@10.31.0`。每次 trial 分别记录 `bootstrap_pnpm` 与 `task_pnpm`；不为匹配 bootstrap 而改动题目的包管理器版本。

全新依赖 checkout 可用下面的命令放入被忽略的 `.artifacts/` 目录：

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

填写清单时使用最后一步实际产生的插件包，并检查它的 SHA-256、任务目录树哈希和所选镜像 digest；runner 会在执行前复核。仅有 `check` 成功，不能证明固定镜像能拉取，也不能证明容器里的 DSH 挂钩有效。

检查入口使用以下哈希函数；请替换成自己的绝对路径：

```sh
python3 -c 'from pathlib import Path; from bench.deepswe.config import digest, tree_digest; print(digest(Path("/absolute/path/plugin.tgz"))); print(tree_digest(Path("/absolute/path/deep-swe/tasks/TASK_ID")))'
```

清单是 `schema=1` 的 JSON 对象，顶层字段为 `schema`、`phase`、`selection_rule`、`paths`、`versions`、`tasks`、`arms`、`repeats`、`model`、`jev`、`conditions`、`budget`、`prices`。参考[示例清单](manifest.example.json)了解字段，核对主模型路由，再把示例路径、哈希、任务、Jev 模型、凭据引用名、价格来源、上下文窗口和预算换成本批次的值。示例里刻意保留的零和负数占位会让 `check` 失败，直到填入真实计划。每题还必须指定 Docker 平台。`check` 不启动 Agent 或下载镜像就能验证这些值；`run` 则在启动 trial 前拉取对应平台、固定 digest 的镜像。若服务端模型使用浮动别名，必须设置 `model.floating_alias`；本地提交固定后也不能保证远端模型实现不变。

runner 同一时间只运行一个 trial。清单必须显式选择 `conditions.sandbox` 为 `workspace-write`，或为另行授权的批次选择 `danger-full-access`；两组使用同一种模式。未知模式会被拒绝，权限检查失败也不会静默切换模式。`danger-full-access` 表示在**隔离的任务 Docker 容器内**不受 DSH 沙箱限制；Docker 仍采用默认非特权设置，不增加 capability、不更改 seccomp、不添加宿主挂载。组别顺序会在观察结果前按题目和重复序号轮换。Agent 与 verifier 时限是必填项。显式的 `budget.max_batch_spend_usd` **只是提示阈值**：provider 用量可能延迟到达，在途请求也可能产生费用，这条执行路径不能保证硬美元上限。要求 `hard_usd_cap` 的清单会被拒绝。`budget.usage_incomplete_policy` 必须选 `halt` 或 `continue-with-unknown`；不能把提示性估算当成支出保证。

此版本执行时间限制和有限的题目／重复次数，但不强制每轮 step 或 token 上限。应将这些上限记录为未设置，不要暗示支出估算能控制它们。付费批次之前，还需用受控的“未安装插件”对“已安装但全关闭”运行核对 baseline 没有新增 Jev 请求或模型可见内容。这个比较是集成门槛，不是第四个结果组。

任何真实模型 Agent setup 之前，声明的权限模式必须通过执行预检。对 `workspace-write`，`sandbox_precheck.mjs` 使用发布版 DSH `LocalSandboxProvider` 在任务根目录内约束 `/usr/bin/true`，要求 `enforcement: "full"`，并成功执行受限命令。对明确授权的 `danger-full-access`，预检须确认同一个隔离容器内不受 DSH 沙箱限制的命令可以执行，不增加 Docker 权限。检查失败必须在模型请求前拒绝 setup。固定 Vitest 镜像的默认权限下，`workspace-write` 预检已验证为提前拒绝：脚本退出码为 2，标记为 `SANDBOX_UNAVAILABLE`，未提供凭据或调用模型。此前一次隔离探针仅增加 `SYS_ADMIN`，保留 Docker 默认 seccomp，关闭网络，且没有宿主挂载或凭据，结果报 `bwrap: pivot_root: Operation not permitted`；一次性容器已删除。详见[仅本地保存的沙箱审计](../../.artifacts/sandbox-probe/audit-2026-09-30.json)。该镜像不满足 `workspace-write` 条件；另行授权的 `danger-full-access` 比较必须使用新清单和新批次。旧 batch3 结果保留为独立条件，尚无真实 A/B 结论。

非付费容器集成检查可用 `phase: "smoke"`，并提供本地 `model.fixture_module` 与对应的 `model.fixture_sha256`。任何启用 Jev 的组还必须显式使用本地确定性的 Jev endpoint；主模型夹具**不会**替换 Jev 服务。`pilot` 和 `formal` 清单不能使用夹具。夹具 trial 通过只说明所配置的 DSH/Pier/verifier 路径与可观察挂钩工作，不证明付费模型行为或 benchmark 收益。

## 检查、执行、恢复与报告

在 worktree 根目录用 Python 3.12 或更新版本运行；执行 Docker trial 时，CLI 通过 `uv` 启动固定的 Pier 项目。把 `PLAN.json`、`BATCH_DIR`、`SLOT_ID`、`N` 分别换成实际清单、新批次目录、槽位 ID 和尝试序号。真实运行前，先查看 `python3 -m bench.deepswe.cli --help`。首次 `run` 固化新批次，`resume` 读取其中已固化的清单。

```sh
python3 -m bench.deepswe.cli check --manifest PLAN.json
node bench/deepswe/credential_launcher.mjs run --manifest PLAN.json --batch BATCH_DIR --execute
node bench/deepswe/credential_launcher.mjs resume --batch BATCH_DIR --execute
node bench/deepswe/credential_launcher.mjs resume --batch BATCH_DIR --execute --retry-interrupted
python3 -m bench.deepswe.cli reverify --batch BATCH_DIR --slot SLOT_ID --attempt N --execute
python3 -m bench.deepswe.cli report --batch BATCH_DIR --output REPORT.json
```

凭据启动器默认通过 DSH 正常的本地凭据服务解析两个已声明的引用，只在隔离子进程环境中提供密钥值。它使用 DSH 的启动环境和本地凭据 provider，不打开用户 profile 或私人 Session。所需引用不可用时，Pier 启动前便会停止。如果执行环境已经提供专用变量，也可直接运行 `python3 -m bench.deepswe.cli run/resume ... --execute`。两种方式都不会将密钥值写入清单。

主模型 DeepSeek 引用已配置、而 Jev 密钥来自独立来源时，可在启动器的 `run` 或 `resume` 命令末尾加 `--jev-key-stdin`。此选项要求 `jev.credential_env: "JEV_API_KEY"`；启动器仍正常解析主模型引用，并从标准输入读取一行 Jev 密钥，只传入子进程环境。输入来源须受控且不会回显或记录密钥。启动器不关闭终端回显，在普通终端直接键入密钥可能显示出来。不要把密钥放进命令参数、清单或纳入 Git 的文件。

`check` 和 `report` 不调用主模型或 Jev。`run` 与 `resume` 可启动产生费用的 Agent trial，所以要求 `--execute`。首次运行把清单和调度顺序固化在批次目录中。`resume` 沿用该批次，不覆盖已完成的成功或任务失败。只有检查过中断或基础设施失败的槽位、仍有预定重试额度时，才使用 `--retry-interrupted`；使用前先确认原 Pier 进程已结束。`reverify` 用保存的补丁启动新的 Pier verifier trial，不重新调用主模型，但仍使用 Docker，也可能需要准备镜像。重评结果应与原尝试并列保存，不覆盖原记录。

首次真实 `pilot` 只比较 `baseline` 与 `log_admission`。3 题、每组每题 2 次的小预检有助于核对集成链路，不是统计收益结论。题目 ID、模型路由、provider 限额与提示性支出阈值必须为该批次选定；工具没有付费运行默认值，也不提供硬美元上限。

## 阅读证据

批次目录应保持私有，其中有固化的清单与调度、每次尝试的 Pier 结果、Agent 标准输出和错误输出、profile 配置、DSH Session、Jev ledger、收集的补丁、verifier 评分与测试输出，以及离线报告。原始 Session、提示词、工具输出和错误文件可能含仓库数据或敏感文本；发布前须审查和脱敏。运行产物不应与插件源码一起提交。

报告保留每次实际尝试，包括失败和重试。按题目 ID、题目校验和及重复序号配对：先在每题内部汇总重复，再比较配对任务。不能挑最后一次或最好的一次，也不能把同题重复运行当作新增独立题目。缺少 verifier、Session、ledger 或用量字段表示**未知或不完整**，不是零；明确记录的零与未知不同。估算费用来自清单中注明来源的价格和可获得的逐次用量，不是服务商账单。主模型与 Jev 用量分开，已记录的失败调用也计入消耗。若工具另行启动模型请求而没有 usage，须单列可见请求次数与未知费用；如 batch4 所示，不能把主模型与 Jev 的估算相加后称为完整总成本。

官方 `reward=1` 表示独立 verifier 定义的测试通过。报告另外说明 Agent 是否正常结束且无需真人；超时尝试的补丁也可能通过测试。F2P/P2P 计数与原始 verifier 输出是测试行为的权威证据。测试数全零，单凭这一点不能断定基础设施故障。Jev ledger 有调用，也不能单独证明删减后的日志进入了模型，或完成核查要求的补做真正执行。现有记录无法证明的参与指标会标为不可观测。

实际发起原生提问或 Retry/Cancel 请求时，记录 `needs-human` 并停止无人值守 trial；最终答复文本里只是提出问题，则作为普通输出保存，交给 verifier 评分。runner 不替 Agent 答题，也不批准原生提权。如果固定的 headless profile 无法暴露所需的交互或完成生命周期，应停在集成验证阶段，不能把事件缺失当成插件无参与。

## 限制与上游材料

首版只覆盖声明的三个组别、一个 DSH 版本，以及支持的 DeepSWE/Pier 格式。它不评估 Goal 监督、多 Agent 纠正、插话分流、workspace 审批、一般意义上的补丁质量，也不能证明 Jev 判断在所有场景里语义正确。即使本地输入已固定，provider 的模型别名和共享缓存仍可能变化；记录运行时间和组别顺序。重评已有补丁验证的是 verifier 可重复性，不是 Agent 可重复性。

本项目适配器参考公开的 [DeepSWE 任务格式](https://github.com/datacurve-ai/deep-swe/blob/0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea/README.md) 与 [Pier 执行 API](https://github.com/datacurve-ai/pier/blob/4d3c14041d16443f3f9f460dcdf23629994a304e/README.md)。分发复制材料前，查阅它们的 Apache-2.0 许可证，以及题目仓库和容器镜像各自的许可。不要把参考补丁、隐藏 verifier 测试、既往结果或其他组的补丁挂载进 Agent 环境。
