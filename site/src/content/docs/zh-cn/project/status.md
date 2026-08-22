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
  - F-0016
  - F-0015
  - F-0005
---

BearAgent 已有本地 `run/inspect/events` CLI。它把严格 Run profile、OpenAI Responses adapter、SQLite、
固定 Policy、workspace Tools 和有界 Agent Loop 组装到同一入口。自动验收使用 Fake Provider；没有
真实模型 4/5 证据，因此 P1 仍未关闭。

## 已经可以验证

| 已完成部分 | 现在能验证什么 |
|---|---|
| P0 工程基础 | Python/uv 安装、CLI `doctor`、Ruff、Pyright、pytest、CI 和模块依赖检查 |
| F-0001 内部数据类型 | ID、Message、Error 和通用 Event 可以校验、冻结、JSON 往返并生成 schema 快照 |
| F-0002 状态和预算规则 | 12 种 Event 可以推导 Run/Activity 状态；五类预算在新 Activity 前检查 |
| F-0003 SQLite EventStore | Event 与 Run/Activity projection 原子提交；migration、重开、并发和损坏读取有测试 |
| F-0004 模型边界 | Provider-neutral 请求/事件、确定性 adapter 和 OpenAI Responses 流式 adapter |
| F-0006 Tool 执行边界 | 有界 Tool 数据、精确 Registry、默认拒绝 Policy、统一 Executor 和安全失败 |
| F-0007 workspace 只读 Tool | 一层目录列出、分段 UTF-8 读取、普通字符串搜索和跨平台路径边界 |
| F-0008 原子输出与 Artifact | 只向 `outputs/**` 写有限 UTF-8 文本；创建/替换以一次 replace 提交并返回 hash 元数据 |
| F-0016 有界 Agent Loop | 从已提交 Event 构造 Context，串行调用模型与 Tool，保存 v2 事实；五个 Fake 任务在两种 Store 上通过 |
| F-0005 生产 CLI 与查询 | `run/inspect/events`、严格 profile、production composition、分页查询和 human/JSON；零预算/缺凭据保留安全 terminal Run；五个任务通过真实 SQLite/Tools + Fake Provider |
| F-0015 本地文档站 | 中文 Starlight 页面、搜索和 Mermaid 可以在本地构建 |

## P1 还需要决定和检查

- 决定真实模型 API/4-of-5 演练是否继续作为 P1 关闭门；
- 若保留该门，使用同一任务定义、固定配置和预算完成演练；
- 对整个 P1 做一次 Reality Check，核对代码、测试、安装包、文档和失败边界。

F-0005 的完成只关闭 Feature，不自动关闭里程碑，也不把离线 Fake 5/5 描述成真实模型结果。

## 当前明确不能做

- CLI 已具备真实 Provider 的装配路径，但当前没有真实 API 演练证据；
- SQLite 可以保存 Event 和 projection，但进程重启后不会自动继续 Run；
- `inspect/events` 只能查看已提交事实，不能 resume、retry 或修复非终态 Run；
- Tool 请求和 Artifact 已随 v2 Event 写入 Store，但还没有用户 Approval、sandbox、服务器 API 或
  独立 Artifact 查询表；
- 文档站只在本地和 CI 构建，尚未发布到 `docs.bearguin.cn`。

F-0002 的确定性重放只说明“同一串 Event 会算出同一状态”。它不是 P2 的崩溃恢复，也没有
Checkpoint、Attempt 或 `UNKNOWN` 处置。

## 文档怎样保持当前

每个 Feature 完成时，同时更新工程 `docs/`、相关学习页、开发者入口和本页。只有实现事实变化时
才修改状态；单纯改写说明不会把规划能力变成当前能力。
