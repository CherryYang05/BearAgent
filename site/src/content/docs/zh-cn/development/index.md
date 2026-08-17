---
title: 从哪里开始读代码
description: 先找到当前功能的事实，再沿着调用关系进入实现和测试。
bearStatus: implemented
sourceRefs:
  - AGENTS.md
  - architecture/overview
  - ai-development-sop
---

开发者文档不复制 Spec，也不把每个目录重新列一遍。它负责回答三个问题：代码从哪里进入、关键
规则在哪里、什么测试能证明修改没有破坏行为。

## 第一次阅读

1. 先看[当前实现状态](../project/status.md)，避免把路线图当成已有功能；
2. 用[Runtime 各部分怎样协作](../architecture/)理解调用方向；
3. 找到当前 Feature 的 Spec、相关 ADR 和 Plan；
4. 按下面的实现导读进入代码和测试；
5. 修改后运行完整验证，并同步会受影响的学习页和状态页。

## 当前实现导读

- [F-0001：内部数据类型](domain-contracts.md)——ID、Message、Error、Event 以及模型 adapter 的翻译边界；
- [F-0002：状态和预算](run-reducer-and-budgets.md)——具体 Event、Reducer、预算检查和修改顺序；
- [F-0003：SQLite EventStore](sqlite-event-store.md)——transaction、migration、projection 和故障测试；
- [F-0004：ModelProvider](model-provider.md)——Responses 流式翻译、资源上限和安全错误；
- [F-0006：Tool 执行边界](tool-execution-boundary.md)——Registry、参数准备、默认拒绝 Policy 和统一 Executor；
- [F-0007：workspace 只读 Tool](workspace-read-tools.md)——跨平台路径边界、list/read/search 和安全测试；
- [Feature 完成时怎样更新文档](feature-documentation.md)——哪些事实写在 `docs/`，哪些解释写在站点；
- [本地运行文档站](../guides/local-docs.md)——安装、构建和检查 Starlight。

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
