---
title: BearAgent 按什么顺序完成
description: 每个阶段给用户增加什么能力，以及用什么结果判断阶段完成。
bearStatus: mixed
sourceRefs:
  - F-0032
  - roadmap
  - F-0017
  - F-0018
  - ADR-0016
---

BearAgent 不按“已经写了多少模块”关闭阶段。每个阶段都要在同一组仓库与本地文档任务上给用户
一个新的、可复现的结果。

| 阶段 | 当前状态 | 阶段结束时用户得到什么 |
|---|---|---|
| P0 工程基础 | 已完成 | 仓库可以安装、测试，开发规则和模块边界明确 |
| P1 可检查执行 | 历史 gate 已完成；F-0032 本地补强待交付 | 文件任务可以完成，模型和工具的过程、预算与失败可以查看 |
| P2 可恢复执行语义 | 未开始 | 根据证据恢复或停在 UNKNOWN；用相同故障集比较不同策略 |
| P3 授权与隔离执行 | 未开始 | 危险操作和诊断干预必须获准，并且只能在受控 runner 中运行 |
| P4 接入与日常使用 | 未开始 | 安全自托管后，Skill、MCP、Web 和 Memory 依次接入 |
| P5 持续评测 | 未开始 | 汇总 P2/P3 已建立的实验，持续比较版本变化对质量、成本、恢复和安全的影响 |

```mermaid
flowchart TB
    P1["P1：发生了什么？"] --> P2["P2：下一步怎样做才安全？"]
    P2 --> P3["P3：动作是否获准，只能影响哪里？"]
```

## P1：完成一次可检查的文件任务

P1 要接通 SQLite、一个真实模型、受限文件工具、有结束条件的 Agent Loop，以及 `run`、`inspect`、
`events` 命令。写入范围固定为 `outputs/**`。完成时，Fake Provider 必须完成全部 5 个任务；一个
显式选择的真实配置必须完成四个普通任务与安全 canary，非法路径和预算耗尽也要有清楚记录。

P1 已完成 SQLite EventStore、三种模型协议 adapter、Registry、固定 Policy、统一 ToolExecutor、
workspace 读写、原子 Artifact、ContextBuilder、串行 Agent Loop、`run/inspect/events`、Provider
catalog、RunProfile v2、RunCreated v3 和默认关闭的 live runner。五个 Fake 任务与最终离线 Reality
Check 通过；suite v1.1.1 又用 DeepSeek V4 经 production 路径完成四个普通任务与安全 canary，并生成
脱敏 report。F-0018 随后让新 Run 统一写 schema v4，保存声明的 Tool/Policy contract fingerprint，并用
K1-K6 核对 hard process exit 后最后可见的 committed fact。v2-shaped Tool execution evidence 在 v2、v3、
v4 都执行同一条原始请求一致性检查；这仍是事实完整性，不是自动恢复。

P1 只保证已经保存的事实可以查看。进程退出后不会自动继续。

F-0032 的收口审查补上配置访问保护、无覆盖初始化和离线检查；本地验证通过，正式交付证据待记录。
历史真实 gate 与这次离线回归分别记录，不用前者代替新缺陷的修复验收。

当前使用入口见[第一次运行](/zh-cn/learn/first-run/)，完整请求路径和取舍见
[一次请求怎样穿过 BearAgent](/zh-cn/architecture/runtime-flow/)与
[P1 为什么这样设计](/zh-cn/architecture/p1-decisions/)。

## P2：让每次恢复决定都有依据

P2 会把一个逻辑 Activity 和它的实际 Attempt 分开。重试会创建新 Attempt，不会覆盖旧失败。
Runtime 先判断动作是只读、幂等、可核对还是非幂等，再选择复用、重试、reconcile 或
`UNKNOWN`。一个 Error 写着 `retryable`，不能单独授权系统重做外部写入。

先完成 Event-only 重建，再根据重放成本决定是否需要 Checkpoint。加入后，删除它也必须能从完整
Event 重建同一状态。恢复尝试继续消耗同一 Run 的预算；未定价费用不能假装成真实账单上限。

实验清单从 P2 开始记录故障位置、可见证据、策略版本、预测、实际结果和副作用次数。先让规则基线
与一个候选策略可以互换，在同一故障集上比较，之后再稳定公开接口。

## P3：授权和隔离是两道不同的门

P3 把 Policy 扩展为 `ALLOW / DENY / REQUIRE_APPROVAL`。Approval 绑定具体 Run、Tool call、规范化
参数、有效期和一次性 nonce。批准 `write_file(a.txt)` 不能被复用成删除其他文件。

获得 Approval 后，shell 或代码仍只能进入独立 runner。runner 默认断网、限制文件和资源，而且读不到
Provider key、主数据库、宿主根目录或 Docker socket。Approval 不能扩大 runner 边界，sandbox 也不能
代替 Policy。

诊断验证同样会影响环境。验证计划必须限制探测次数、允许扰动与提前终止条件，并在行动前写下预测。
服务恢复不等于诊断正确；是否减少有害动作，应与额外延迟和扰动一起比较。这是待检验的研究假设。

P3 是可信 Runtime 内核的完成线。HTTP API、认证、HTTPS、自托管、Web、MCP 和 Memory 都属于 P4。

## P4：先安全接入，再扩大能力

P4 先增加 HTTP/SSE、单用户认证、Compose 加固、备份和恢复，再依次接入 Skill、MCP、Web UI、
Memory 和受控联网。Tool 数量真实增长后，才决定是否需要 Tool selector 或 deferred loading。

## 阶段怎样关闭

真实任务和失败演练必须能被别人复现；README、架构、代码、测试和状态页要说同一件事；
当前限制必须直接写出。路线图或架构图本身不能作为“已经完成”的证据。
