---
title: 现在实现到了哪里
description: 只列出当前分支中已有代码和测试支持的能力。
bearStatus: implemented
sourceRefs:
  - roadmap
  - F-0001
  - F-0002
  - F-0015
---

BearAgent 当前还不能调用真实模型完成文件任务。已经写入路线图、架构或 ADR 的设计，不等于已经
接通运行入口。

## 已经可以验证

| 已完成部分 | 现在能验证什么 |
|---|---|
| P0 工程基础 | Python/uv 安装、CLI `doctor`、Ruff、Pyright、pytest、CI 和模块依赖检查 |
| F-0001 内部数据类型 | ID、Message、Error 和通用 Event 可以校验、冻结、JSON 往返并生成 schema 快照 |
| F-0002 状态和预算规则 | 12 种 Event 可以推导 Run/Activity 状态；五类预算在新 Activity 前检查 |
| F-0015 本地文档站 | 中文 Starlight 页面、搜索和 Mermaid 可以在本地构建 |

## P1 还需要接通

- Event store 和 SQLite 保存；
- 工具接口、统一执行入口和固定权限规则；
- 工作区读取、搜索和 `outputs/**` 原子写入；
- 一个真实 Model Provider adapter；
- 最小上下文组装和有界 Agent Loop；
- `run`、`inspect`、`events` 命令以及固定评测任务。

这些工作在 Roadmap 中有稳定 Feature ID，但未创建 Spec 的条目仍只是待办。仓库当前没有 active Plan，
下一个 P1 Feature 需要由项目所有者确认后开始。

## 当前明确不能做

- 不能调用真实模型或执行完整 Agent Loop；
- 不能用 SQLite 保存 Run，也不能在进程重启后自动继续；
- 没有实际文件工具、用户 Approval、sandbox 或服务器 API；
- 文档站只在本地和 CI 构建，尚未发布到 `docs.bearguin.cn`。

F-0002 的确定性重放只说明“同一串 Event 会算出同一状态”。它不是 P2 的崩溃恢复，也没有
Checkpoint、Attempt 或 `UNKNOWN` 处置。

## 文档怎样保持当前

每个 Feature 完成时，同时更新工程 `docs/`、相关学习页、开发者入口和本页。只有实现事实变化时
才修改状态；单纯改写说明不会把规划能力变成当前能力。
