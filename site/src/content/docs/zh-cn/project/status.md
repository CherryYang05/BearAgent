---
title: 当前实现状态
description: 区分 BearAgent 已实现能力、正在建设内容和未来 Roadmap。
bearStatus: implemented
sourceRefs:
  - roadmap
  - F-0001
  - F-0015
---

本页只陈述有仓库证据支持的当前状态。Roadmap 中出现的名称不等于已经可用。

## 已完成

| 范围 | 状态 | 证据 |
|---|---|---|
| P0 工程基线 | 已完成 | Python/uv 骨架、CLI doctor、CI、文档治理和测试 |
| F-0001 领域契约 | 已实现 | 类型化 ID、Message、Error、Event envelope 和 schema snapshot |
| F-0015 本地文档站 | 已实现 | Starlight 中文站、本地搜索、Mermaid、学习与架构入口 |

## P1 运行时 Backlog

以下 Feature 名称已经登记在 Roadmap，但尚未创建或实现对应 Spec：

1. F-0002 Run reducer and budgets
2. F-0003 EventStore contract and SQLite adapter
3. F-0004 ModelProvider contract and first adapter
4. F-0005 CLI run/inspect/events
5. F-0006 Tool contract and registry
6. F-0007 Workspace boundary and read tools
7. F-0008 Atomic write tool and artifacts

:::caution[当前不能做什么]
BearAgent 现在还不能调用真实模型完成文件任务，也没有 SQLite Run、ToolRegistry 或可恢复 Agent
Loop。相关页面如果提前解释设计，必须标记为设计或规划中。
:::

## 服务器发布时间

文档站在 P1 期间只本地构建。P1 完成后再单独确认 `docs.bearguin.cn` 的托管、HTTPS、发布权限
和回滚流程，当前仓库中不保存服务器凭证，也没有部署 Job。
