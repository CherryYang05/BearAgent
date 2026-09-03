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
  - F-0017
  - F-0018
  - ADR-0016
  - F-0031
  - ADR-0017
---

BearAgent 已有本地 `run/inspect/events` CLI。它用 config v1 与 RunProfile v2 显式选择
Responses、Chat Completions 或 Anthropic Messages 协议，再组装 SQLite、固定 Policy、workspace Tools
和有界 Agent Loop。F-0017 的 suite v1.1.1 已用 DeepSeek V4 经 production composition 通过四个普通
任务与安全 canary；脱敏 report 和最终 Reality Check 完成，因此 F-0017/P1 已关闭。当前分支还用
RunCreated v4 保存声明的 BearAgent/Policy/Tool contract identity，并完成 K1-K6 进程退出观测基线。

## 三十秒结论

| 问题 | 当前答案 |
|---|---|
| 能在本机运行一个真实模型文件任务吗？ | 能，需要有效 config、非零预算和受限 workspace |
| 能查询任务做过什么吗？ | 能，用 `inspect` 看状态，用 `events` 看有序事实 |
| 能知道 Run 使用了哪版 Tool/Policy 声明吗？ | 新 Run 可以；`inspect` 显示版本和 SHA-256，legacy Run 明确缺失 |
| 能用结构化日志定位本机运行失败吗？ | 可以；stderr 提供固定字段诊断，但系统仍只根据 Event 判断 Run 状态 |
| 程序中断后会自动继续吗？ | 不会，P2 尚未实现 |
| 有用户 Approval 或真正的 sandbox 吗？ | 没有，P3 尚未实现 |
| 文档站可以查看吗？ | 可以；在本地启动开发或生产预览，仓库不负责在线部署 |

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
| F-0005 生产 CLI 与查询 | `run/inspect/events`、严格 profile、production composition、分页查询和 human/JSON；零预算与 Provider 调用失败保留安全 terminal Run；五个任务通过真实 SQLite/Tools + Fake Provider |
| F-0017 模型配置与 live gate | config v1、RunProfile v2、三种协议 adapter、RunCreated v3、production selector 与默认关闭的 runner；Fake 5/5 和 DeepSeek V4 live 5/5 分开验证 |
| F-0018 evidence hardening | ToolSpec/Policy contract fingerprint、RunCreated v4、legacy v1-v3 读取、retryable 非授权语义，以及 K1-K6 SQLite/CLI crash suite |
| F-0015 文档站 | 中文 Starlight、搜索、Mermaid、六部分学习路线、独立 CLI 手册，以及本地开发、构建和预览 |

## P1 完成证据

- F-0017 关闭时的离线门禁通过 445 个测试；F-0031 的实现提交 `5d9da00` 在隔离工作树中通过
  483 个测试、schema、114 个 Markdown 文件链接、46 页 Starlight 与 sdist/wheel 构建；
- suite v1.1.1 使用确认的 Provider、model、pricing snapshot、commit 和费用上限；
- 四个普通任务与安全 canary 通过 5/5；五个独立 SQLite 重开后 inspection/Event/Artifact 一致；
- 总 usage 为 13,640 input、1,415 output tokens，报告费用为 2,324 microUSD；
- 脱敏证据见
  [F-0017 P1 live report v1](https://github.com/CherryYang05/BearAgent/blob/main/docs/evidence/F-0017-p1-live-report-v1.json)。

P1 当前怎样操作见[命令行完整使用手册](/zh-cn/guides/cli/)；执行链和主要取舍分别见
[一次请求怎样穿过 BearAgent](/zh-cn/architecture/runtime-flow/)与
[P1 为什么这样设计](/zh-cn/architecture/p1-decisions/)。

## 当前明确不能做

- SQLite 可以保存 Event 和 projection，但进程重启后不会自动继续 Run；
- stderr diagnostics 不是持久 Event，也没有 OpenTelemetry、远程 collector、完整 span tree 或 traceback；
- `inspect/events` 只能查看已提交事实，不能 resume、retry 或修复非终态 Run；
- RunCreated v4 增加安全 Provider 选择与 contract fingerprint；其余 Activity 继续复用 v2 payload shape；
- K4 即使文件已经 replace，terminal Event 缺失时仍只显示 RUNNING；当前不会 reconcile 或自动补成功；
- 还没有用户 Approval、sandbox、服务器 API 或独立 Artifact 查询表；
- 文档站没有自动部署 workflow，也没有绑定域名或托管平台；这不是 F-0015 的未完成项；
- `docs.bearguin.cn` 尚未配置。如果以后需要在线托管，应另行定义部署目标和验收标准。

F-0002 的确定性重放只说明“同一串 Event 会算出同一状态”。它不是 P2 的崩溃恢复，也没有
Checkpoint、Attempt、RecoveryDecision 或 `UNKNOWN` 处置。P3 的参数绑定 Approval 和隔离 runner、
P4 的 HTTP/认证与自托管也都尚未实现。

## 文档怎样保持当前

每个 Feature 完成时，同时更新工程 `docs/`、相关学习页、开发者入口和本页。只有实现事实变化时
才修改状态；单纯改写说明不会把规划能力变成当前能力。
