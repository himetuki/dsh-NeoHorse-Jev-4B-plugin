## 直接答案

这是一组“历史冻结 run 的一次性 driver”结果：6 个预先固定的合成案例，baseline 与只开启 `file-ranking` 的条件各运行 1 次，共 12 个 trial。12/12 正常结束、usage 完整、fixture 未变，模型工具调用中没有网页搜索、bash、edit 或 write。4 个在 1–40 个候选范围内的开启组各完成 1 次 Jev operation，共 69 个候选问答；0 个匹配和 41 个候选都没有 Jev operation。

目标排序结果很具体：16 个候选案例的真目标从 Jev 请求序列第 13 位排到第 5；40 个候选案例的两个真目标从第 26、27 位排到第 1（0.80）和第 3（0.76），一个 `parser/token/refresh-access-token.ts` 诱饵排第 2（0.77）。每种情况都只运行一次，不能据此推断一般排序准确率或通用效率收益。

## 固定条件

两组使用同一套候选上限 40、显示上限 12 的文件排序条件；唯一 profile 开关差异是 `file-ranking`。任务指令要求只读。每例各运行一次，不自动重试；agent 预算 120 秒。工具集不含网页工具，记录中也没有网页请求。本次不使用 verifier，不产生 DeepSWE 分数。

记录的运行版本为 DeepSeek `deepseek-flash`（`high`）、Jev `jev-1.13.0`、DSH `0.1.7-rc.2`、Node `24.14.1`。输入清单所记 DeepSWE source commit 为 `0b9fabbb63b9104d678fe965e1632f2dd9eaa2ea`，插件 source commit 为 `cd041b90a3a291d832d75030ea92975501280f63`，Pier commit 为 `4d3c14041d16443f3f9f460dcdf23629994a304e`。插件 tar SHA-256 为 `3a77e6e2b777df295fada449cfa1d23462d7d513a101f7ec6c63eb52693631b2`；任务镜像为 `sha256:11087ec4eb0320e80546ad5eda89c67938e72be69cbb7c6730cf9baf88dc7556`。

冻结输入锁 SHA-256 为 `0f864ca6679677a7098e1481120c660893116ab725552aacf5c275a698ecfe0e`。锁内保存的 driver 输入 SHA 可在[结构化结果](./results.json)中查阅；其中包括 `cases.py`、`selection_suite.py`、`analyze.py` 与 `launch.mjs` 的哈希。Session 记录的运行窗口是 2026-10-01 02:43:34.992–02:56:10.749 UTC。suite lock 和 manifest 没有单独记录输入冻结时间，因此此窗口只表示 trial 活动时间。

| 案例 | 候选数与真值 | baseline 原生位置 | 开启组请求位置 → Jev 排名（分数） | 源码读取 baseline → 开启组 | spill 回读 baseline → 开启组 |
|---|---:|---:|---|---:|---:|
| `zero` | 0；无目标 | — | 无 Jev 请求 | 0 → 0 | 0 → 0 |
| `single` | 1；`src/jev-suite/single/auth/access-token-refresh.ts` | 1 | 1 → 1（0.81） | 1 → 1 | 0 → 0 |
| `twelve` | 12；`src/jev-suite/twelve/12-circuit-reset.ts` | 2 | 2 → 1（0.75） | 1 → 1 | 0 → 0 |
| `nested-sixteen` | 16；`src/jev-suite/nested-sixteen/auth/session/refresh.ts` | 13 | 13 → 5（0.75） | 4 → 4 | 0 → 1 |
| `multi-forty` | 40；`src/jev-suite/multi-forty/auth/session/refresh-access-token.ts`、`src/jev-suite/multi-forty/auth/session/token-store.ts` | 26、27 | 26 → 1（0.80）、27 → 3（0.76） | 40 → 5 | 0 → 1 |
| `over-forty-one` | 41；`src/jev-suite/over-forty-one/security/lease-expiration.ts` | 28 | 超过 40 个候选上限，旁路且无 Jev 分数 | 1 → 1 | 0 → 0 |

在 40 候选案例中，另一个诱饵 `src/jev-suite/multi-forty/parser/token/refresh-access-token.ts` 排第 2（0.77）；`src/jev-suite/multi-forty/auth/schema/token-store.ts` 排第 4（0.75）。开启组完成 5 次源码读取和 1 次完整排序 spill 回读；baseline 读取 40 个源码文件。16 候选案例两组都读 4 个源码文件，开启组另回读 1 次 spill，不能声称这个案例减少了源码读取。41 候选案例两组都保留原生位置 28；40 候选上限触发旁路，没有“前 40 个评分、尾部未评分”的部分排序。

全部真值目标都出现在各自最终回答并被读过。主模型共有 40 条带 usage 的消息，输入 32,142、输出 12,718、缓存读取 304,256、缓存写入 0 tokens；4 个 Jev operation 合计输入 4,250、输出 1,296 tokens。Jev operation 均成功，69 个问题都有对应答案。主模型与 Jev 费用均为按记录 usage 和冻结单价算出的估算值，不是账单：baseline 主模型 $0.017517384，开启组主模型 $0.009212352，开启组 Jev $0.000178500，12 次合计 $0.026908236。

本次估算使用的冻结费率（每百万 tokens）：

| 费率表 | 输入 | cache read | cache write | 输出 | 来源快照 |
|---|---:|---:|---:|---:|---|
| 主模型 | $0.30 | $0.006 | $0.30 | $1.20 | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)，peak 2026-09-30 |
| Jev 1.13.0 | $0.042 | $0 | $0 | $0 | [Typesafe models](https://docs.typesafe.ai/models)，2026-09-30；无单独 client cache usage |

Jev 行里的零是冻结费率，不表示本次实测了零 cache tokens。费率快照与来源字符串也保存在 [results.json](./results.json) 中。

逐槽 operation、attempt、receipt、usage、latency 与工具计数见[公开回执](./receipts.json)。详细结构化结果和候选得分表见[results.json](./results.json)。

## 边界与验证

这 12 个结果验证了该冻结版本在六个固定合成路径案例中的一次功能链：原生 `grep` 保持不变，符合条件的 `glob` 结果可排序并按需从 spill 回读；0 候选和 41 候选不调用 Jev。运行各一次，候选、诱饵、提示和源码内容都是人工合成；分数表示本次候选排序，不是源码判断正确率、成功概率或成本收益估计。读文件数是这些固定提示下的观测，不能外推为插件的一般效率收益。

此结果不是正式 DeepSWE 评测，也没有比较 stage-navigation。稍后的公开 `bench/selection` 管线是整理后的后续材料，运行基线已包含第 12 个功能；本次没有用该管线重跑，也不能把它说成 suite lock 哈希对应的原 driver。后续维护管线的说明见[选择管线 README](../../../bench/selection/README.zh-CN.md)。本报告描述的是原历史冻结 run，并非该维护管线的新 driver 重跑。
