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
---

BearAgent 已有可由 Python 调用的有界 Agent Loop，但还不能从 CLI 启动真实模型文件任务。已经写入
路线图、架构或 ADR 的更晚设计，不等于已经接通运行入口。

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
| F-0015 本地文档站 | 中文 Starlight 页面、搜索和 Mermaid 可以在本地构建 |

## P1 还需要接通

- `run`、`inspect`、`events` 命令和 production adapter 组装；
- 使用相同任务定义完成真实模型 4/5 退出演练。

F-0016 已实现。F-0005 在 Roadmap 中有稳定 Feature ID，但开始前仍需按仓库流程确认 Spec、ADR 和
Plan；没有 Spec 的条目不能授权实现。

## 当前明确不能做

- 不能从 CLI 启动一次真实模型文件任务，也没有 `inspect/events` 人类输出；
- SQLite 可以保存 Event 和 projection，但进程重启后不会自动继续 Run；
- application Loop 可以调度 ModelProvider port，但生产 OpenAI adapter 尚未与 CLI、SQLite 和 workspace
  配置组装；
- Tool 请求和 Artifact 已随 v2 Event 写入 Store，但还没有用户 Approval、sandbox、服务器 API 或
  独立 Artifact 查询表；
- 文档站只在本地和 CI 构建，尚未发布到 `docs.bearguin.cn`。

F-0002 的确定性重放只说明“同一串 Event 会算出同一状态”。它不是 P2 的崩溃恢复，也没有
Checkpoint、Attempt 或 `UNKNOWN` 处置。

## 文档怎样保持当前

每个 Feature 完成时，同时更新工程 `docs/`、相关学习页、开发者入口和本页。只有实现事实变化时
才修改状态；单纯改写说明不会把规划能力变成当前能力。
