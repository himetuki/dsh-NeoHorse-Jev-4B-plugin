# Glob Ranking Frozen-Run Evidence

本目录归档 DeepSeek Harness Jev `glob` 文件排序的历史冻结运行结果。它记录一次性的实验 driver 与一次运行，不是后续 `bench/selection` pipeline 的源码快照或复跑结果。

This folder records one historical frozen run of Jev `glob` file ranking. It is evidence for that run, not a source snapshot or replay result from the later public selection pipeline.

## 文件 / Files

- [中文结果说明](./public-results.zh-CN.md)：条件、逐案例观测与外推边界。
- [结构化结果](./results.json)：合成目标、候选排序与分数、冻结版本和哈希。
- [公开回执](./receipts.json)：每槽状态、工具计数、模型 usage 与 Jev operation/attempt 元数据。

## 后续管线 / Later pipeline

- [后续选择管线说明](../../../bench/selection/README.zh-CN.md)

后续维护管线经过整理，使用的 main 已包含第 12 个功能。本目录中的冻结输入锁和插件 tar 不对应维护管线哈希；本次实验没有使用新 driver 重跑，也没有测量 stage-navigation。
