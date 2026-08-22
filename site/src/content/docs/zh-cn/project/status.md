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
| F-0007 workspace 只读 Tool | 一层目录列出、分段 UTF-8 读取、普通字符串搜索和路径逃逸拒绝 |
| F-0008 原子输出与 Artifact | `outputs/**` UTF-8 原子创建/替换，以及路径、大小和 SHA-256 元数据 |
| F-0015 文档站 | 中文 Starlight 页面、搜索、Mermaid、sitemap 和 404 可以构建；Pages 发布配置进行中 |

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

## 当前明确不能做

- SQLite 可以保存 Event 和 projection，但进程重启后不会自动继续 Run；
- 模型 adapter 可以翻译一次 Responses 流，但尚未由 ContextBuilder 或 Runtime 调度；
- 四个 workspace Tool 已通过统一入口单独验证，但没有 Agent Loop、用户 Approval、sandbox 或服务器 API；
- 文档站的 GitHub Pages workflow 已写入当前分支；合并、启用 Pages Source 并首次部署前，公开地址
  仍不可用。`docs.bearguin.cn` 还没有配置。

F-0002 的确定性重放只说明“同一串 Event 会算出同一状态”。它不是 P2 的崩溃恢复，也没有
Checkpoint、Attempt、RecoveryDecision 或 `UNKNOWN` 处置。P3 的参数绑定 Approval 和隔离 runner、
P4 的 HTTP/认证与自托管也都尚未实现。

## 文档怎样保持当前

每个 Feature 完成时，同时更新工程 `docs/`、相关学习页、开发者入口和本页。只有实现事实变化时
才修改状态；单纯改写说明不会把规划能力变成当前能力。
