---
title: BearAgent Roadmap
status: accepted
---

# BearAgent 项目路线图

## 1. 先记住三个问题

BearAgent 不追着 Agent 产品的功能清单前进。P1 至 P3 沿着同一条 Runtime 主线，每个阶段只回答
一个可以通过故障演练验证的问题：

```text
P1 发生了什么？
        ↓
P2 根据已保存事实，下一步怎样做才安全？
        ↓
P3 这个动作是否获准，又只能影响哪里？
```

- **P1：Inspectable Execution / 可检查执行。** 保存模型、Tool、预算、Error 和 Artifact 事实；
- **P2：Recoverable Execution Semantics / 可恢复执行语义。** 区分逻辑 Activity 与实际 Attempt，
  根据副作用证据选择复用、重试、reconcile 或 `UNKNOWN`；
- **P3：Authorized and Isolated Execution / 授权与隔离执行。** 危险动作先取得绑定具体参数的
  Grant/Approval，再进入受控 runner。

阶段只由可复现的用户结果关闭。模块存在、ADR 被接受、Checkpoint 能写入或 sandbox 能启动，都
不能单独算完成。

## 2. 固定产品范围

首个场景仍是仓库与本地文档研究：在指定 workspace 内查找和比较资料，并把结果写入
`outputs/**`。同一组任务会继续用于 P2 的中断恢复和 P3 的授权、隔离演练。

P0 至 P3 保持单用户、单 Agent、单个 Runtime 进程、SQLite 和 CLI 优先。所有外部动作继续经过
`Registry -> prepare -> Policy -> ToolExecutor`。模型、Prompt、Skill、workspace 内容和 Tool 输出
都不能创建权限。主 Runtime 进程不执行模型生成的 shell。

以下能力不会提前挤进 P2/P3：

- Agent routing、multi-agent 和通用 Workflow engine；
- MCP、Web、Memory、自动模型/Tool 路由和大规模 Tool search；
- 语义化通用死循环判断；
- 公开 HTTP 服务、多用户、分布式 worker 和 exactly-once 承诺。

## 3. 阶段总览

| 阶段 | 状态 | 用户得到什么 | 关闭阶段的关键证据 |
|---|---|---|---|
| P0 工程基础 | 已完成 | 仓库可安装、测试，边界和开发规则明确 | 干净安装、CLI、CI、依赖边界、文档规则 |
| P1 可检查执行 | 已完成 | 固定本地文件任务可完成，过程和失败可查看 | Fake 5/5、真实 5/5、路径拒绝、预算终止、完整 Event |
| P2 可恢复执行语义 | 未开始 | 中断后根据事实选择安全的下一步 | kill point、Attempt、恢复决策、不重复写入、`UNKNOWN` |
| P3 授权与隔离执行 | 未开始 | 危险动作获准后只在受控边界内执行 | Approval 篡改阻断、等待批准恢复、runner 资源与 secret 隔离 |
| P4 接入与日常使用 | 未开始 | 安全自托管后，Skill、MCP、Web 和 Memory 依次接入 | 新入口不绕过 Event、恢复、Policy 和 runner 路径 |
| P5 持续评测 | 未开始 | 可以比较质量、成本、恢复和安全回归 | 固定数据集、执行路径断言、跨版本报告 |

P3 是可信 Runtime 内核的完成线。P4 才是把这个内核变成日常可访问产品的阶段。

## 4. 已完成的基础

### P0：工程基础

**状态：已完成（2026-08-09）。** 详细验收见
[F-0000](../specs/F-0000-p0-engineering-baseline.md)。

P0 建立 Python 3.12、uv、CI、CLI、模块依赖检查、测试替身，以及 Spec/ADR/Plan 和文档规则。

### P1：可检查执行

**P1 状态：已完成。** F-0001 至 F-0008、F-0015 至 F-0018 均已实现。Runtime gate 在
2026-08-23 完成；F-0015 随后完成书籍化文档重构和本地站点验收。F-0018 是进入 P2 前的增量 evidence
hardening；它不重写 P1 exit criteria，也不把已关闭的 P1 基线改回进行中。

P1 已接通：

- 类型化领域数据、Event、Reducer 和五类 hard budget；
- SQLite EventStore、projection、migration 和重开查询；
- 三种显式模型协议 adapter、Provider 配置和有界 Context；
- 默认拒绝 Policy、workspace 读写 Tool、原子 Artifact 和串行 Agent Loop；
- `run/inspect/events` CLI、Fake 任务集、真实模型 gate 和脱敏证据。

F-0017 关闭时的离线门禁通过 445 个测试、schema、链接、35 页站点、sdist/wheel 和隔离 CLI smoke。
suite v1.1.1 使用 DeepSeek V4 经 production composition 完成四个普通任务和一个安全 canary，结果为
5/5。证据见 [F-0017 P1 live report](../evidence/F-0017-p1-live-report-v1.json)。F-0018 关闭时进一步通过
474 个测试、K1-K6 与 45 页站点构建；后续 2026-09-02 全仓审计又补齐 schema v4 Tool evidence 的
跨 Event 一致性回归。

P1 只保证已保存事实可查。F-0018 让新 Run 记录可信 Tool/Policy contract identity，并用
hard-process 测试验证最后 committed fact 的可见性。进程退出后仍不会自动继续；timeout 也不会撤销
可能已经发生的副作用。

F-0019 是不改变 P1 退出状态的追加 hardening：它补齐 accepted F-0016 中的安全结构化日志，只从已经
提交的 Event 输出固定 envelope/耗时/错误码，并为 bootstrap、CLI 和 EventStore 边界增加有限运行诊断。
系统不会读取这些日志来判断 Run 状态或决定 P2 恢复。该 Feature 已实现，当前 F-0019 编号下的
implementation evidence 为 `08ee141`，对应 Plan 已完成。

F-0015 提供独立的 Starlight 文档站、渐进式学习路线、CLI 手册和源码导读。它可以本地开发、构建
和预览，普通 CI 负责验证；在线托管与自动部署不属于 F-0015，也不再作为 P1 的关闭门。

## 5. P2：可恢复执行语义

**状态：未开始。** P1 已关闭；开始实现前仍要逐个接受对应 Feature Spec。

### 5.1 阶段目标

> Runtime 在进程中断或 Tool 结果不确定后，只根据已提交事实判断下一步；已经确认的副作用不重复，
> 安全操作可以有界重试，可核对的操作先 reconcile，无法确认的操作明确进入 `UNKNOWN`。

P2 的核心不是“多 retry 几次”，而是让每次恢复决定都有可审计的依据。

### 5.2 四层恢复语义

#### 第一层：状态重建

- 完整 Event 永远是事实来源；
- Event-only replay 与 `Checkpoint + tail Event` 必须得到相同 RunState 和 state hash；
- Checkpoint 只加速读取，缺失、损坏或版本不兼容时必须回到完整 Event；
- 启动扫描只识别非终态 Run 和最后一个已保存边界，不在这一层盲目恢复外部调用。

#### 第二层：Activity 与 Attempt 分开

Activity 表示一个逻辑动作。Attempt 表示这个动作的一次真实执行尝试。重试必须创建新 Attempt，
不能覆盖旧失败，也不能让 Event 看起来像只执行过一次。

每个 Attempt 至少关联：请求、开始/结束边界、失败类别、deadline、幂等键和可选 Receipt。模型重试、
Tool 重试和网络 transport 重试必须能够区分。

#### 第三层：先分类，再决定

现有 `ToolSideEffect` 说明动作会影响哪里，`ToolRetrySafety` 只给出 P1 的粗粒度提示。P2 需要增加
独立的恢复语义，至少区分：

```text
READ_ONLY        没有外部副作用
IDEMPOTENT       使用同一幂等键重复执行，结果不再变化
RECONCILABLE     可以通过目标状态或 Receipt 核对
NON_IDEMPOTENT   无可靠证据时不能自动重做
```

失败也至少分成输入无效、短暂基础设施故障、永久故障、权限拒绝和副作用结果不明。一个
`retryable=true` 不能单独授权 Runtime 重做有副作用的动作。

#### 第四层：恢复策略

```text
READ_ONLY + transient failure       -> 在次数、deadline 和 Run budget 内新建 Attempt
IDEMPOTENT                          -> 使用同一幂等键查询或重试
RECONCILABLE                        -> 先 reconcile，再决定复用或重试
NON_IDEMPOTENT + insufficient proof -> UNKNOWN
```

恢复决定本身写成 Event。用户必须能看到系统为什么继续、为什么没有重试，或为什么停在
`UNKNOWN`。

### 5.3 操作控制

- `pause`、`resume`、`cancel`、`retry` 先保存用户意图，再影响调度；
- cancel 后不创建新的 Activity；已经开始的外部副作用仍按实际证据处理；
- retry 针对明确 Activity 创建新 Attempt，不重写旧 Event；
- 重复命令必须幂等，或返回稳定、可查询的冲突；
- `UNKNOWN` 需要 inspect、人工确认结果和审计入口，不能只成为数据库里的隐藏状态。

### 5.4 故障演练

至少在这些边界强制结束 Runtime：

1. 模型请求 Event 已保存、完成 Event 未保存；
2. Tool Attempt 已开始、结果 Event 未保存；
3. `workspace.write` 临时文件完成、`os.replace` 之前；
4. `os.replace` 已发生、ToolResult/Event 尚未保存；
5. cancel 意图已保存、adapter 尚未停止；
6. projection transaction 回滚、Checkpoint 缺失或损坏。

每个 kill point 都要断言副作用次数、最终状态、恢复决定和可见 Error，而不只断言“程序能重启”。

### 5.5 hard budget、软提示和重复失败

P1 的模型次数、Tool 次数、token、费用和总时间 hard budget 继续作为最终兜底。P2 的 retry 也消耗
同一 Run budget，不能建立一套绕过预算的隐藏计数。

接近上限时向 Context 提供剩余预算提示，或者阻止“相同 Tool + 相同规范化参数 + 相同确定性失败 +
无进展”的重复动作，可以作为后续小型 guardrail。它们不替代恢复语义，也不是 P2 关闭条件。项目
不承诺通用语义死循环检测。

### 5.6 P2 明确不做

Grant/Approval、sandbox、shell、公开 API、Routing、Memory、MCP、任意调用栈或 token stream 的字节级
恢复、不可查询外部写的 exactly-once、多 worker 和通用 Workflow engine。

### 5.7 P2 Definition of Done

- Event-only 与 Checkpoint replay 在 Windows/Linux 得到等价状态；
- kill-point suite 能从仅有的持久事实恢复，并记录每次 RecoveryDecision；
- 已确认 workspace 写不重复，replace 前后残留都能正确 reconcile；
- 只读与幂等操作只在明确上限内重试，每次 Attempt 都可查；
- 非幂等且证据不足的动作不会自动重做，而是进入可处理的 `UNKNOWN`；
- cancel 后不再调度新 Activity，重复控制命令不制造重复转换；
- golden trace 可用 Fake adapter 重放，并精确断言外部副作用次数。

## 6. P3：授权与隔离执行

**状态：未开始。必须在 P2 的恢复闭环完成后启动。**

### 6.1 阶段目标

> 任何危险副作用在执行前都必须取得可审计授权，并且只能在受控执行边界内运行；模型只提出
> Intent，不持有权限。

P3 回答“能不能做、可以影响哪里”。它不再同时承担公网 API 和产品部署。

### 6.2 授权门

P1 的 `ALLOW / DENY` 升级为：

```text
ALLOW
DENY
REQUIRE_APPROVAL
```

Grant 表达主体、动作、资源和限制。Approval 绑定具体 Run、Tool call、规范化参数 hash、有效期和
一次性 nonce。批准 `git.push` 到一个分支，不能被复用到另一个分支；批准写一个路径，也不能被
修改为删除其他资源。

登录身份、Prompt、AgentConfig、Skill 和 ToolResult 都不能创建 Grant。Policy 仍在 Tool 真正执行前
重新检查可信 ToolSpec 和规范化参数。

### 6.3 隔离门

shell/code Tool 只通过独立 `SandboxBackend` runner：

- 无特权用户、只读 rootfs、每 Run 独立 workspace；
- CPU、内存、PID、wall time、stdout/stderr 和 Artifact 大小受限；
- 网络默认关闭，需要的目标另行授权；
- 不挂载 Provider key、主数据库、用户 home、宿主根目录或 Docker socket；
- runner 不可用时 Tool 明确不可用，不回退到 host subprocess。

sandbox 不能代替 Policy，Approval 也不能扩大 runner 的文件、网络或资源边界。两道门都通过后动作
才可执行。

### 6.4 与 P2 的连接

- 等待 Approval 是持久状态，重启后仍能查询、批准或拒绝；
- 批准或拒绝必须成为 Event，并能恢复到同一个 Policy 结果；
- runner timeout 不等于副作用未发生，仍按 P2 的 Attempt/Receipt/reconcile/`UNKNOWN` 处理；
- Approval 被篡改、过期、重放或跨 Run 使用时，不创建 runner Attempt；
- 取消等待批准的 Run 后，旧 Approval 不能重新激活执行。

### 6.5 P3 明确不做

公开 HTTP API、HTTPS/DNS、Web UI、MCP、Skill、Memory、浏览器、任意通用联网、多用户、组织 RBAC、
插件市场、PostgreSQL、Redis、queue 和多 worker。它们属于 P4 或更晚阶段。

### 6.6 P3 Definition of Done

- 参数绑定 Approval 的篡改、过期、重放和跨 Run 使用全部被拒绝；
- Prompt injection、workspace 内容和 Tool 输出无法授予权限；
- 等待批准、批准后尚未执行、runner 结果未保存三个中断边界都能安全恢复；
- runner 读不到 Provider key、主数据库、宿主根目录、用户 home 和 Docker socket；
- 文件、网络、进程、资源和输出越界全部产生有限、可审计失败；
- runner 不可用时没有 host fallback；
- 每个危险动作都能从 Intent、Policy、Grant/Approval、Attempt、Receipt 和最终 Event 串回完整证据。

## 7. P4：接入与日常使用

**状态：未开始。**

P4 先把可信 Runtime 变成可安全访问的单用户服务，再扩大 Tool 和上下文表面：

1. HTTP API、SSE 续接和单用户认证；
2. Compose 加固、HTTPS、备份与空目录恢复；
3. 一个版本化只读 Skill，证明说明文件不能扩大权限；
4. 一个受控 MCP Tool，证明外部 Tool 仍经过 Policy、Attempt、Event 和 runner 边界；
5. Web UI、带来源且可删除的 Memory，以及受控联网；
6. Tool 数量真实增长后，再决定静态分组、deferred loading 或 Tool selector。

Agent routing、multi-agent、通用 progress detector 和大规模 Tool search 不因“业界常见”自动进入 P4；
必须先出现现有单 Agent/固定 Tool subset 无法解决的任务证据。

## 8. P5：持续评测

**状态：未开始。**

P5 把 P1 任务、P2 恢复演练和 P3 安全演练接入统一追踪，比较模型、Prompt、Skill 和 Tool 版本带来
的答案、执行路径、成本和延迟变化。评测从 P1 就存在；P5 负责持续、跨版本地运行这些证据。

## 9. P6+：只有需求证明后再做

- Child Run 形式的多个 Agent；
- schedule、webhook 和长 timer；
- 浏览器和电脑控制；
- 向量检索；
- 消息渠道；
- PostgreSQL、多 worker、queue 和 lease；
- Temporal 或其他 durable Workflow engine；
- 多用户和租户隔离。

进入任一项前都要给出触发证据，例如 SQLite 写竞争达到阈值、任务需要跨天 timer，或固定 Tool subset
已无法承载真实任务，而不是因为参考项目已经支持。

## 10. 阶段边界速查

| 问题 | 阶段 |
|---|---|
| model/tool/token/cost/time hard budget | P1 已实现 |
| 有界 Context、ToolResult 截断、Tool timeout | P1 已实现 |
| 本机安全结构化运行诊断 | P1 hardening F-0019 |
| Attempt、失败分类、retry/backoff | P2 |
| Checkpoint、启动扫描、resume/cancel | P2 |
| idempotency、Receipt、reconcile、`UNKNOWN` | P2 |
| Grant、参数绑定 Approval | P3 |
| shell/code、文件/网络/secret 隔离 | P3 |
| HTTP API、认证、HTTPS、自托管 | P4 |
| Skill、MCP、Web、Memory | P4 |
| Tool routing | P4 出现规模证据后 |
| generalized loop/progress detection | P4/P5 研究项，不是承诺 |
| OpenTelemetry、完整 span 和跨版本 trace | P5 |
| 多 Agent、分布式执行 | P6+ |

## 11. Feature Backlog

Feature ID 在 Spec 创建后保持稳定。未创建 Spec 的名称只表示计划范围；开始前必须创建 Spec 并声明
milestone。2026-09-04，项目所有者明确要求把新增的 P1 日志 Feature 调整为紧接 F-0018 的 F-0019，
并把尚未创建 Spec 的 P2/P3/P4 占位 ID 依次顺延。这是进入 P2 前的一次性编号整理，不改变任何
Feature 的范围或 milestone；本次映射完成后继续遵守稳定 ID 规则。

### P1（基线已关闭；F-0019 追加 hardening 已完成）

1. [F-0001：内部 ID、Message 和 Error](../specs/F-0001-domain-ids-messages-errors.md)
2. [F-0002：Run/Activity 状态和预算](../specs/F-0002-run-reducer-activity-lifecycle-budgets.md)
3. [F-0003：EventStore、SQLite、projection 和 migration](../specs/F-0003-event-store-sqlite-projections.md)
4. [F-0004：模型接口和首个真实 adapter](../specs/F-0004-model-provider-first-adapter.md)
5. [F-0005：`run/inspect/events` CLI](../specs/F-0005-run-inspect-events-cli.md)
6. [F-0006：Tool Registry、Policy 和 Executor](../specs/F-0006-tool-registry-executor-policy.md)
7. [F-0007：workspace 只读 Tool](../specs/F-0007-workspace-read-tools.md)
8. [F-0008：原子输出和 Artifact](../specs/F-0008-atomic-output-artifacts.md)
9. [F-0015：可以连续阅读的 Starlight 文档书](../specs/F-0015-local-starlight-docs-site.md) — implemented
10. [F-0016：有界 Context 和串行 Agent Loop](../specs/F-0016-bounded-context-agent-loop.md)
11. [F-0017：模型服务配置与真实 gate](../specs/F-0017-configurable-model-providers-live-gate.md)
12. [F-0018：可信 Run contract identity 与 crash observability](../specs/F-0018-p1-evidence-hardening.md) — implemented
13. [F-0019：安全结构化运行诊断](../specs/F-0019-safe-structured-diagnostics.md) — implemented

F-0015 的文档内容、本地站点、构建和阅读体验已经实现；部署到某个在线平台不在该 Feature 范围内。

### P2（计划；均未创建 Spec）

1. F-0020：Event-only 状态重建、Checkpoint fallback 和启动检查
2. F-0021：Attempt、失败分类、恢复语义和有界 retry
3. F-0022：幂等键、Receipt、reconcile 和 `UNKNOWN` 处置
4. F-0023：pause/resume/cancel/retry 命令与完整 kill-point suite

### P3（计划；均未创建 Spec）

1. F-0024：Grant、三态 Policy 和持久化参数绑定 Approval
2. F-0025：SandboxBackend、隔离 runner 和受控 shell/code Tool

### P4（计划；均未创建 Spec）

1. F-0026：HTTP API、SSE 续接和单用户认证
2. F-0027：Compose 加固、HTTPS、备份和空目录恢复
3. F-0028：版本化只读 Skill
4. F-0029：受控 MCP Tool
5. F-0030：Web UI
6. F-0031：有来源、可删除的 Memory 和上下文压缩

如果一个条目在写 Spec 时仍无法独立验收，保留现有 ID 的核心范围，并用新的全局 ID 拆出后续
Feature。一个 Plan 不得同时实现整个阶段。

## 12. 维护这份路线图

- 每个 Feature 完成时，对工程 `docs/`、学习页、开发者导读和当前状态逐项记录更新路径或 `N/A`
  原因；只有事实或读者路径变化时才修改对应页面；
- 每个阶段完成时，同步本 Roadmap、学习地图、架构总结和阶段结果；
- 外部项目只能提供概念和方案对照，不能建立 BearAgent 当前能力；
- 同时最多一个 active 主 Plan；
- 阶段只由可复现退出证据关闭，不按主观百分比关闭。
