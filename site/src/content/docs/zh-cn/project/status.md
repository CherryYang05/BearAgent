---
title: 现在实现到了哪里
description: 只列出当前分支中已有代码和测试支持的能力。
bearStatus: implemented
sourceRefs:
  - roadmap
  - F-0001
  - F-0002
  - F-0003
  - F-0004
  - F-0006
  - F-0007
  - F-0008
  - F-0015
  - F-0005
  - F-0017
---

BearAgent 当前还不能调用真实模型完成文件任务。路线图和架构中的设计，不等于已经接通运行入口。

## 已经可以验证

| 已完成部分 | 现在能验证什么 |
|---|---|
| P0 工程基础 | Python/uv 安装、CLI `doctor`、Ruff、Pyright、pytest、CI 和模块依赖检查 |
| F-0001 内部数据类型 | ID、Message、Error 和通用 Event 可以校验、冻结、JSON 往返并生成 schema 快照 |
| F-0002 状态和预算规则 | 12 种 Event 可以推导 Run/Activity 状态；五类预算在新 Activity 前检查 |
| F-0003 SQLite EventStore | Event 与 Run/Activity projection 原子提交；migration、重开、并发和损坏读取有测试 |
| F-0004 模型边界 | Provider-neutral 请求/事件、确定性 adapter 和首个 OpenAI Responses 流式 adapter |
| F-0006 Tool 执行边界 | 有界 Tool 数据、精确 Registry、默认拒绝 Policy、统一 Executor 和安全失败 |
| F-0007 workspace 只读 Tool | 一层目录列出、分段 UTF-8 读取、普通字符串搜索和跨平台路径边界 |
| F-0008 原子输出与 Artifact | 只向 `outputs/**` 写有限 UTF-8 文本；创建/替换以一次 replace 提交并返回 hash 元数据 |
| F-0016 有界 Agent Loop | 从已提交 Event 构造 Context，串行调用模型与 Tool，保存 v2 事实；五个 Fake 任务在两种 Store 上通过 |
| F-0005 生产 CLI 与查询 | `run/inspect/events`、严格 profile、production composition、分页查询和 human/JSON；零预算/缺凭据保留安全 terminal Run；五个任务通过真实 SQLite/Tools + Fake Provider |
| F-0015 文档站 | 中文 Starlight、搜索、Mermaid、由浅入深的 P1 路线、独立 CLI 手册和 Pages 发布配置 |

Python package 已能在本地构建 sdist 和 wheel，但这不表示 `bearagent` 已经发布到 PyPI。正式发布前
仍要确定许可证、确认 PyPI 项目名归属、完成隔离安装与发布演练。发布后的安装路径见
[从 PyPI 安装 BearAgent](../guides/install-from-pypi.md)。

想了解最新完成的执行边界，可以先读面向初学者的
[F-0016 前，BearAgent 已经完成什么](../learn/before-agent-loop.md)，再读
[一个 Tool 请求为什么要过四道检查](../learn/tool-execution-boundary.md)，最后按
[Tool 执行边界代码导读](../development/tool-execution-boundary.md)进入代码和测试。

## P1 完成证据

- 最小上下文组装和有界 Agent Loop，把模型、ToolExecutor 与 EventStore 接成一条 Run；
- 保存完整模型结果、规范化 ToolRequest/ToolResult、配置版本和 Artifact 来源；
- `run`、`inspect`、`events` 命令以及固定评测任务。

这些工作目前仍只是待办，不是可用能力。下一个 P1 功能需要由项目所有者确认后开始。

P1 当前怎样操作见[命令行完整使用手册](../guides/cli.md)；执行链和主要取舍分别见
[一次请求怎样穿过 BearAgent](../architecture/runtime-flow.md)与
[P1 为什么这样设计](../architecture/p1-decisions.md)。

## 当前明确不能做

- SQLite 可以保存 Event 和 projection，但进程重启后不会自动继续 Run；
- `inspect/events` 只能查看已提交事实，不能 resume、retry 或修复非终态 Run；
- Tool 请求和 Artifact 已随 v2 Event 写入 Store，但还没有用户 Approval、sandbox、服务器 API 或
  独立 Artifact 查询表；
- Pages workflow 只在 `main` 或手动触发时部署；F-0015 PR #14 仍待本次改动验证与合并，之后还要
  确认仓库 Pages Source 和公开 URL；
- `docs.bearguin.cn` 尚未配置，当前发布目标是 GitHub Pages 项目地址。

F-0002 的确定性重放只说明“同一串 Event 会算出同一状态”。它不是 P2 的崩溃恢复，也没有
Checkpoint、Attempt、RecoveryDecision 或 `UNKNOWN` 处置。P3 的参数绑定 Approval 和隔离 runner、
P4 的 HTTP/认证与自托管也都尚未实现。

## 文档怎样保持当前

每个 Feature 完成时，同时更新工程 `docs/`、相关学习页、开发者入口和本页。只有实现事实变化时
才修改状态；单纯改写说明不会把规划能力变成当前能力。
