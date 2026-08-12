---
title: 当前实现状态
description: 区分 BearAgent 已实现能力、正在建设内容和未来 Roadmap。
bearStatus: implemented
sourceRefs:
  - roadmap
  - F-0001
  - F-0002
  - F-0003
  - F-0004
  - ADR-0010
  - ADR-0003
  - ADR-0009
  - F-0015
---

本页只陈述有仓库证据支持的当前状态。Roadmap 中出现的名称不等于已经可用。

## 已完成

| 范围 | 状态 | 证据 |
|---|---|---|
| P0 工程基线 | 已完成 | Python/uv 骨架、CLI doctor、CI、文档治理和测试 |
| F-0001 内部数据格式 | 已实现 | 类型化 ID、Message、Error、Event 通用外壳和 JSON Schema 快照 |
| F-0002 状态与预算 | 已实现 | Run/Activity schema、12 种 payload、纯 Reducer、五维 budget gate |
| F-0003 持久事实 | 已实现 | EventStore 接口规则、SQLite WAL、数据格式 v1、原子 Run/Activity 查询视图 |
| F-0004 模型边界 | 已实现 | 统一内部请求/事件、替代实现、OpenAI Responses 流式适配器、失败分类 |
| F-0015 本地文档站 | 已实现 | Starlight 中文站、本地搜索、Mermaid、学习与架构入口 |

## P1 运行时 Backlog

以下 Feature 尚未实现：

1. F-0006 Tool contract, registry, executor and baseline policy gate
2. F-0007 Workspace boundary and read tools
3. F-0008 Atomic write tool and artifacts
4. F-0016 Minimal ContextBuilder, bounded loop, Agent config and eval task pack
5. F-0005 CLI run/inspect/events

:::caution[当前不能做什么]
BearAgent 现在已有可调用真实 OpenAI Responses 流式接口的生产适配器，也能把合法 Event 与
Run/Activity 查询视图原子写入 SQLite；但两者还没有被 Agent Loop/Application command 连接，
因此仍不能完成文件任务，也没有 ToolRegistry 或 CLI Run。
P1 完成后也只承诺执行事实可检查；Checkpoint、崩溃后自动恢复、`UNKNOWN` 处置、Approval 与
sandbox 分别属于 P2/P3。相关页面如果提前解释设计，必须标记为设计或规划中。
:::

## 当前阶段门

F-0004 已完成；P1 仍未关闭，下一 Feature 必须再次由项目所有者确认后建立 active Plan。
阶段关闭时必须复现真实 CLI 文件任务、非法路径拒绝、预算终止和 Activity/Event/Artifact 检查；
不能用已接受 Roadmap 或架构图代替这些实现证据。

## 服务器发布时间

文档站在 P1 期间只本地构建。P1 完成后再单独确认 `docs.bearguin.cn` 的托管、HTTPS、发布权限
和回滚流程，当前仓库中不保存服务器凭证，也没有部署 Job。

## 文档同步状态

从 F-0015 开始，每个 Feature 都必须同时更新工程 `docs/`、初学者学习路径、开发者文档和本页。
每个 P 阶段关闭时还要更新[阶段与里程碑](milestones.md)，避免网站只显示功能列表而缺少完整的
学习与实现脉络。
