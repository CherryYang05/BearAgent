---
title: 从哪里开始读代码
description: 先找到当前功能的事实，再沿着调用关系进入实现和测试。
bearStatus: implemented
sourceRefs:
  - AGENTS.md
  - architecture/overview
  - ai-development-sop
  - F-0016
  - F-0005
  - F-0017
---

开发者文档不复制 Spec，也不把每个目录重新列一遍。它负责回答三个问题：代码从哪里进入、关键
规则在哪里、什么测试能证明修改没有破坏行为。

## 先顺着一次调用读，不要按目录字母序读

```text
interfaces/cli/main.py        解析命令，调用 bootstrap/application
        ↓
bootstrap.py                  读取可信配置并组装具体 adapter
        ↓
application/agent_loop.py     推进一次 Run，不实现 SDK 或文件细节
        ↓
runtime/*                     Context、Reducer、预算、Policy、Executor
        ↓
ports/*                       核心要求外部实现提供什么
        ↓
adapters/model|sqlite|tools   把 SDK、数据库和文件系统翻译到内部契约
```

第一遍只跟成功路径。第二遍选择一个失败，例如非法路径或预算耗尽，查看 Error 怎样变成 Event 和最终
RunState。第三遍再读安全测试，确认你看到的是受测试约束的边界，不只是代码恰好这样写。

### 一个 30 分钟源码实验

1. 在 `interfaces/cli/main.py` 找到 `run` 命令调用；
2. 在 `bootstrap.py` 找到 config/profile 怎样选择 adapter 和 Tool；
3. 在 `application/agent_loop.py` 找到 Model 与 Tool Activity 前后的 Event append；
4. 在 `runtime/tool_executor.py` 找到 Registry、prepare、Policy 与 adapter 的唯一执行路径；
5. 运行 `uv run pytest tests/integration/test_agent_loop.py -q`，再把测试中的一个 Tool 名改错，观察有限失败。

不要在练习后保留故意破坏的测试改动。

## 第一次阅读

1. 先看[当前实现状态](/zh-cn/project/status/)，避免把路线图当成已有功能；
2. 如果还没实际运行过 P1，先走一遍[CLI 完整手册](/zh-cn/guides/cli/)；
3. 用[Runtime 各部分怎样协作](/zh-cn/architecture/)和[P1 架构取舍](/zh-cn/architecture/p1-decisions/)
   理解调用与依赖方向；
4. 找到当前 Feature 的 Spec、相关 ADR 和 Plan；
5. 按下面的实现导读进入代码和测试；
6. 修改后运行完整验证，并同步会受影响的使用、学习、开发者和状态页面。

## 当前实现导读

- [F-0001：内部数据类型](/zh-cn/development/domain-contracts/)——ID、Message、Error、Event 以及模型 adapter 的翻译边界；
- [F-0002：状态和预算](/zh-cn/development/run-reducer-and-budgets/)——具体 Event、Reducer、预算检查和修改顺序；
- [F-0003：SQLite EventStore](/zh-cn/development/sqlite-event-store/)——transaction、migration、projection 和故障测试；
- [F-0004/F-0017：ModelProvider 与协议 adapter](/zh-cn/development/model-provider/)——显式 protocol factory、三种流式翻译、Event v3 和 live gate；
- [F-0006：Tool 执行边界](/zh-cn/development/tool-execution-boundary/)——Registry、参数准备、默认拒绝 Policy 和统一 Executor；
- [F-0007：workspace 只读 Tool](/zh-cn/development/workspace-read-tools/)——跨平台路径边界、list/read/search 和安全测试；
- [F-0008：原子输出与 Artifact](/zh-cn/development/atomic-output-artifacts/)——同目录暂存、原子提交、结果元数据和故障窗口；
- [F-0016：有界 Agent Loop](/zh-cn/development/agent-loop/)——Context、v2 Event、串行模型/Tool 调度、故障窗口和固定任务；
- [F-0005：生产 CLI 与查询](/zh-cn/development/run-cli/)——Run profile、composition root、inspect/events、JSON 契约和失败边界；
- [Feature 完成时怎样更新文档](/zh-cn/development/feature-documentation/)——哪些事实写在 `docs/`，哪些解释写在站点；
- [本地运行文档站](/zh-cn/guides/local-docs/)——安装、构建和检查 Starlight。

## 不同问题去哪里找答案

| 你要确认什么 | 首选位置 |
|---|---|
| 这个功能必须做到什么 | Feature Spec |
| 为什么选择当前方案 | ADR |
| 准备按什么顺序实现 | Implementation Plan |
| 当前模块如何连接 | Architecture |
| 行为是否真的成立 | 代码、测试和可复现命令 |
| 当前版本能否使用 | 站点状态页 + implemented Spec |

聊天讨论可以提出问题，但不会自动改变这些事实。决定只有写入仓库并通过审查后才生效。
