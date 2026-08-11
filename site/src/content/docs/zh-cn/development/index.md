---
title: BearAgent 开发者入口
description: 从工程事实、模块边界、Feature 工作流和验证证据理解 BearAgent。
bearStatus: implemented
sourceRefs:
  - AGENTS.md
  - architecture/overview
  - ai-development-sop
---

开发者文档帮助你从“知道概念”继续走到“能解释、修改和验证实现”。它不会取代工程 `docs/`：
Spec、ADR、代码和测试仍是事实来源，这里负责建立阅读顺序和代码地图。

:::note[内容状态：当前开发流程]
本页描述的文档同步和验证流程已经写入仓库规则。Runtime 功能是否可用仍以
[当前实现状态](../project/status.md)为准。
:::

## 推荐阅读顺序

1. 阅读[产品定位](../project/positioning.md)，确认功能是在强化核心证据还是只增加能力宽度。
2. 阅读[BearAgent 架构概览](../architecture/)理解 Core、Port 和 Adapter 的依赖方向。
3. 阅读当前 Feature 的 Spec、ADR 和 Implementation Plan，确认目标、边界与取舍。
4. 通过本区的实现导读找到代码、测试和验证命令。
5. 修改后同时更新工程文档、初学者学习路径、开发者文档与当前状态。

## 当前实现导读

- [F-0001：领域契约实现](domain-contracts.md)：ID、Message、Error、Event envelope 和 schema snapshot。
- [F-0002：Run reducer 与预算](run-reducer-and-budgets.md)：typed payload、状态转换、usage 与预算门。
- [Feature 文档同步规则](feature-documentation.md)：每个 Feature 和每个 P 阶段如何关闭。
- [本地运行文档站](../guides/local-docs.md)：安装、预览并验证 Starlight 构建。

## 证据地图

| 问题 | 去哪里找 |
|---|---|
| 为什么要做 | Feature Spec |
| 为什么选择这种设计 | ADR |
| 当前做到哪个切片 | Implementation Plan |
| 系统现在如何分层 | Architecture |
| 行为是否真实成立 | 代码、测试和可复现命令 |
| 初学者怎样理解 | `site/.../learn/` 与架构导读 |
| 开发者怎样修改 | `site/.../development/` |

开发者页面只解释已经被这些证据支持的事实；尚未实现的设计必须明确标注。
