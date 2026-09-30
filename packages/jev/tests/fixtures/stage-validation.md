# 阶段导航本地 Web 验收夹具

此夹具在 worktree 的 `.artifacts/stage-validation/home` 中创建独立 DSH Web profile。公开脚本只生成合成 Session 和 localhost System One 响应；它们不需要主模型凭据。

在本 worktree 根目录执行：

```sh
export DSH_HOME="$(pwd)/.artifacts/stage-validation/home"
node packages/jev/tests/fixtures/stage-session-seed.mjs
node packages/jev/tests/fixtures/stage-session-check.mjs
node packages/jev/tests/fixtures/stage-profile.mjs init
node packages/jev/tests/fixtures/stage-system-one-server.mjs
```

服务打印 `success`、`invalid`、`quota`、`held`、`stats` 等 localhost 地址。另一个终端用打印的 `success` 地址配置 profile；配置命令会写入测试专用 dummy credential，并让 `stage-navigation` 初始保持关闭：

```sh
export DSH_HOME="$(pwd)/.artifacts/stage-validation/home"
node packages/jev/tests/fixtures/stage-configure.mjs http://127.0.0.1:PORT/v1/systemone/stage-success
```

主代理完成本分支构建和安装包后，以**绝对路径**安装该包，再启动官方发布版 DSH。启动命令固定浏览器目录选择器，剥离继承的 DeepSeek 主模型环境变量，并把工作目录设为隔离夹具目录：

```sh
node packages/jev/tests/fixtures/stage-profile.mjs install /absolute/path/to/plugin.tgz
node packages/jev/tests/fixtures/stage-profile.mjs start
```

合成 Session id 为 `stage-navigation-fixture-20260929`。其四轮分别为正常双步骤、正常双步骤、含错误工具结果的用户中止轮、失败轮；共六个闭合 step。首步含 17 个 Think 块、两个工具调用及配对结果和一个无正文的失败 attempt；第二轮末步是无工具最终回复。每步正文含 `STAGE_TnSm` 标记，localhost 服务据当前目标标记给出固定标签、confidence 与 probabilities。服务 `GET /stats` 显示请求数，`GET /dump` 仅在 localhost 返回完整测试请求；`POST /reset` 清零内存计数。原 Session 中的假密钥只能用于检查发送体脱敏，绝不能作为真实凭据。

浏览器验收顺序：初始关闭时不显示“阶段导航”标签；开启后仅浏览、切轮、展开原文时 `/stats` 仍为零；手动分析第一轮只发两次判断，原文保留首步完整 Think 与两个工具结果；分析第二轮后两轮同名阶段各自定位；第三轮保留用户中止和工具错误。重复分析已有有效目标、关闭当前阶段页再开启、重启同一 profile 读取缓存，都不增加请求。`invalid`、`quota`、`held` 地址用于显式失败与取消测试，改变 endpoint 后须重新确认所分析结果的配置身份和状态。
