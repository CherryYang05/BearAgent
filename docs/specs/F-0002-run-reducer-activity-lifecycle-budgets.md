---
title: "Feature: Run reducer, Activity lifecycle and budgets"
status: implemented
spec_id: F-0002
milestone: P1
owner: CherryYang05
created: 2026-08-11
last_updated: 2026-08-11
implemented_in: "PR #5"
related_adrs:
  - ADR-0001
  - ADR-0002
  - ADR-0007
  - ADR-0009
---

# Feature: Run reducer, Activity lifecycle and budgets

## 1. Background / Problem

F-0001 提供了类型化 ID、通用 Event envelope 和安全错误，但没有定义具体 Event payload、
Run/Activity 状态或预算语义。F-0003 的 EventStore、F-0004 的 Agent Loop 和 F-0005 的
`run inspect` 如果各自推断状态或维护计数，会产生不一致的终态、非法转换和预算绕过。

F-0002 先建立一个无 I/O 的状态内核：相同的有序 Event 必须得到相同的不可变 `RunState`，
且任何新 Activity 在进入事件流前都能用同一套规则检查预算。P1 只承诺执行事实可检查，
不在本 Feature 中承诺进程重启后自动续跑。

## 2. Goals

- G-1：定义 P1 可达的 Run 与 Activity 生命周期及不可变状态模型。
- G-2：为状态转换定义版本化、Provider/Tool/Store 无关的 Event payload。
- G-3：提供严格、纯函数式 reducer，从有序 Event 构造或推进同一 `RunState`。
- G-4：统一模型迭代、token、费用、wall time 和 Tool 次数的预算限制与记账语义。
- G-5：预算耗尽和非法事件产生稳定、安全、可测试的失败，不静默继续调度。
- G-6：把新增公共领域契约纳入 JSON schema snapshot/compatibility 基线。

## 3. Non-goals

- NG-1：不实现 Agent Loop、ModelProvider 调用、Tool 执行或 CLI Run。
- NG-2：不实现 SQLite、projection transaction、migration、Checkpoint 或 startup recovery。
- NG-3：不实现 pause/resume/cancel/retry、Activity attempt、receipt 或 `UNKNOWN`；这些属于 P2。
- NG-4：不实现 `WAITING_APPROVAL`、Grant、Approval 或 sandbox；这些属于 P3。
- NG-5：不预测 Provider 实际 token/费用，也不强制中断已经开始的外部调用。
- NG-6：不引入并行 Activity、Multi-Agent 或新的生产依赖。

## 4. Terms and assumptions

- **Model iteration**：一个被接受的 `ModelCallRequested`，在该 Event 进入状态时计数一次。
- **Tool call**：一个被接受的 `ToolCallRequested`，在该 Event 进入状态时计数一次。
- **Token usage**：Provider adapter 后续归一化并写入模型完成/失败 Event 的 input + output token。
- **Cost**：使用非负整数 `micro-USD`（百万分之一美元）记账，避免浮点金额比较。
- **Wall time**：从 `RunStarted.occurred_at` 到候选新 Activity 时间的 UTC 时间差。
- **Active Activity**：状态为 `PENDING` 或 `RUNNING` 的 Activity；P1 同时最多一个。
- Event sequence 决定事实顺序；时间戳用于时间预算和检查，不替代 sequence 排序。

所有五类 limit 都显式存在并允许为 0，以支持“立即耗尽”的确定性测试；实现同时设置安全上限，
拒绝负数、布尔值和无界大整数。

## 5. User scenarios

### Scenario A：确定性状态重建

Given 同一个 Run 的连续 Event sequence，When 内存执行路径或后续 projection 重放这些 Event，
Then reducer 产生值相等的 `RunState`、Activity 列表和预算用量。

### Scenario B：非法转换 fail closed

Given 一个终态 Run、重复 Activity ID、sequence gap 或错误的 Activity 完成 Event，When reducer
处理该 Event，Then 返回稳定校验失败，且输入状态不被修改。

### Scenario C：预算耗尽

Given Run 已达到相关模型迭代/Tool 次数限制，或已达到 token/费用/deadline，When Runtime
准备请求下一个 Activity，Then 预算检查返回 `budget_exhausted`，调用方只能记录 `RunFailed`，
不能记录新的 Activity request。

### Scenario D：已开始 Activity 的事实完整性

Given Activity 已在 deadline 前通过预算检查并开始，When 它在 deadline 后完成或报告超额实际
token/费用，Then完成/失败事实仍被 reducer 接受并记账；预算阻止的是后续 Activity，不丢弃
已经发生的事实。

## 6. Functional requirements

- FR-1：P1 `RunStatus` 只包含 `QUEUED / RUNNING / SUCCEEDED / FAILED`；后两者为终态。
- FR-2：P1 `ActivityStatus` 包含 `PENDING / RUNNING / SUCCEEDED / FAILED`，Activity kind 只包含
  `MODEL / TOOL`。
- FR-3：状态 Event v1 至少包含 `RunCreated`、`RunStarted`、`ModelCallRequested`、
  `ModelCallStarted`、`ModelCallCompleted`、`ModelCallFailed`、`ToolCallRequested`、
  `ToolCallStarted`、`ToolCallCompleted`、`ToolCallFailed`、`RunSucceeded` 和 `RunFailed`。
- FR-4：每个支持的 `event_type + schema_version` 映射到一个拒绝未知字段的 Pydantic payload；
  reducer 对未知 event type/version fail closed，不静默忽略。
- FR-5：第一个 Event 必须是 sequence 1 的 `RunCreated`；后续 Event 必须属于同一 `run_id`、
  sequence 连续，且符合当前 Run/Activity 转换。
- FR-6：Activity request 创建 `PENDING` Activity，started Event 转为 `RUNNING`，completed/failed
  Event 转为对应终态；Activity ID、ModelCall ID 和 ToolCall ID 在一个 Run 内不可复用。
- FR-7：P1 同时最多一个 active Activity；Run 只有在没有 active Activity 时才能进入终态；
  终态后不再接受 Event。
- FR-8：`RunState` 至少保存 `run_id`、`session_id`、status、budget limits/usage、Activity 序列、
  started/completed time、terminal error 和 last sequence；模型保持冻结并拒绝未知字段。
- FR-9：预算 limit 至少包含 `max_model_iterations`、`max_tokens`、`max_cost_microusd`、
  `max_wall_time_ms` 和 `max_tool_calls`；usage 使用非负整数。
- FR-10：`ModelCallRequested` 增加 model iteration；`ToolCallRequested` 增加 Tool call；模型
  completed/failed payload 中的实际 input/output token 与 cost 增加累计 usage。
- FR-11：调度 Model Activity 时检查下一次 model iteration；调度 Tool Activity 时检查下一次
  Tool call；token、费用和 wall time 是两类 Activity 共用的全局门槛。
- FR-12：budget gate 使用“当前 usage + 将请求的相关次数”判断。实际 token/费用只有结果返回后
  才知道，允许一次已开始的模型调用使实际 usage 超过 limit，但之后不得请求新 Activity。
- FR-13：Activity started/completed/failed 与 Run terminal Event 用于记录已经发生的事实，不因
  Event 时间已过 deadline 或 completion usage 超限而被丢弃。
- FR-14：预算拒绝返回包含 dimension、limit、consumed 和 requested 的稳定、安全信息，错误
  category/code 为 `budget / budget_exhausted`；非法 Event/转换使用稳定 validation error。
- FR-15：reducer 与 budget gate 不读系统时钟、不执行 I/O、不修改输入对象；候选 UTC 时间由
  调用方显式传入或使用 Event 的 `occurred_at`。
- FR-16：Run/Activity/budget/payload schema 进入公共 schema registry 与 snapshot；core 不 import
  Provider SDK、Typer、SQLite、adapter 或外层框架。

## 7. Interfaces

计划新增以下内部 Python 契约；精确函数签名以实现和生成 schema 为准：

```text
domain.runs
  RunStatus / ActivityKind / ActivityStatus
  BudgetLimits / BudgetUsage / BudgetExhaustion
  ActivityState / RunState

domain.run_events
  typed v1 payloads + event_type/schema_version registry

runtime.reducer
  reduce_event(previous_state, event) -> RunState
  reduce_events(events) -> RunState

runtime.budgets
  check_activity_budget(state, activity_kind, occurred_at)
```

F-0002 可为 F-0001 的 `ErrorCode` 增加稳定的非法事件/状态转换代码；不会改变已有代码含义。
这些类型是 BearAgent 内部跨端口契约，不承诺作为独立第三方 SDK API。

## 8. State and data model

```text
RunCreated -> QUEUED
QUEUED + RunStarted -> RUNNING
RUNNING + RunSucceeded -> SUCCEEDED
RUNNING + RunFailed -> FAILED

ActivityRequested -> PENDING
PENDING + ActivityStarted -> RUNNING
RUNNING + ActivityCompleted -> SUCCEEDED
RUNNING + ActivityFailed -> FAILED
```

- `RunCreated` payload 保存 `session_id` 与完整 budget limits。
- 模型 Activity payload 使用 `activity_id + model_call_id`；Tool Activity 使用
  `activity_id + tool_call_id`，request 另外保存受限 `tool_name`。
- 模型完成/失败 payload 保存非负 `input_tokens`、`output_tokens` 和 `cost_microusd`；未知 usage
  不能伪装成负数或非有限值，具体 Provider 归一化由 F-0004 决定。
- failed/terminal payload 只保存 `ErrorInfo`，不保存原始异常、堆栈或 Provider response。
- reducer 返回新的不可变 state；Activity 使用按 request 顺序保存的不可变序列。
- F-0003 将决定数据库列、transaction 和 projection schema；本 Feature 不创建 migration。

## 9. Failure and recovery semantics

- 非连续 sequence、跨 Run Event、未知 event/version、重复 ID、非法转换和错误 payload 在 reducer
  边界失败，不产生部分 state。
- budget gate 拒绝后，调用方必须记录带 `BUDGET_EXHAUSTED` 的 `RunFailed`；F-0004 负责把该门
  接到 Agent Loop，F-0002 只固定纯规则和构造能力。
- 已接受并开始的 Activity 可以在 limit/deadline 之后记录完成或失败；P1 不强制取消外部调用。
- 相同完整 Event sequence 必须得到相同 state；这为 P2 replay 提供基础，但 P1 不扫描或续跑
  非终态 Run。
- reducer 发现损坏 Event stream 时不猜测、不跳过、不合成成功状态。

## 10. Security and privacy

- Event payload、错误和预算输入均视为不可信边界数据，拒绝 unknown fields、错误类型和超限整数。
- reducer 只解释白名单 event type/version；模型或 Tool 输出不能发明 Event 来改变状态或预算。
- budget limits 只能来自创建 Run 的受信 application command，不能由模型消息或 ToolResult 提高。
- 新 payload 不保存认证头、secret、原始 Provider 对象或完整敏感 Tool 输出。
- 本 Feature 没有文件、网络、数据库或 shell 副作用。

## 11. Observability

- `RunState` 暴露 last sequence、Run/Activity status、预算 limits/usage 和安全 terminal error。
- 每个 Activity 保留 request/start/end 时间与对应 typed ID，供 F-0003 projection 和 F-0005 inspect。
- budget exhaustion 明确指出耗尽 dimension 与数值，不要求解析自由文本。
- 本 Feature 不增加 trace backend 或日志依赖。

## 12. Rollout and rollback

- 当前没有持久 Run 数据，F-0002 可以在 F-0003 冻结 SQLite schema 前一次性引入这些契约。
- 回退删除新增 domain/runtime 模块并恢复 schema snapshot；不需要数据库 migration 或数据转换。
- F-0003 接入持久 Event 后，payload 的不兼容变化必须增加 schema version/upcaster，不能原地改义。

## 13. Acceptance criteria

- AC-1：合法 Run lifecycle Event 可从 `None` reducer 到 QUEUED、RUNNING 和一个终态，结果冻结且
  JSON round-trip 后值相等。
- AC-2：合法 Model/Tool Activity 可按 PENDING -> RUNNING -> SUCCEEDED/FAILED 转换并正确关联
  typed ID；同一 Run 不允许 active Activity 重叠。
- AC-3：sequence gap、跨 Run、重复 ID、未知 event/version、终态后 Event 和非法转换均稳定失败，
  输入 state 保持不变。
- AC-4：模型迭代和 Tool 次数在 request Event 记账；token/费用在模型 completion/failure Event
  记账，失败 Activity 的已报告 usage 不丢失。
- AC-5：五类预算的边界值和耗尽值都有测试；耗尽后新 Activity request 被拒绝并可生成安全
  `BUDGET_EXHAUSTED` ErrorInfo。
- AC-6：已开始 Activity 的 completion/failure 即使超过 deadline 或造成 token/费用超限仍可记录，
  但后续 Activity request 被拒绝。
- AC-7：对同一 Event sequence 重放多次得到值相等的 state，reducer 不依赖全局 clock、随机数或 I/O。
- AC-8：新增公共 schema 与 snapshot 一致；现有 F-0001 schema 无意外不兼容变化。
- AC-9：architecture import boundary、Ruff、Pyright、pytest、docs check 和站点构建通过。

## 14. Test plan

- Unit：Run/Activity 全部合法转换、不可变性、ID 唯一性、sequence/run 一致性和纯重放。
- Unit：五类预算的未耗尽、恰好耗尽、prospective count、实际 usage 超限和 deadline 边界。
- Contract：Run/Activity/budget/Event payload JSON schema snapshot；F-0001 schema 回归。
- Integration：不适用；F-0003/F-0004 分别接入 store 与 loop。
- Recovery：Event-only fold 的确定性测试；不做进程 crash/startup recovery。
- Security：未知 event/version、恶意 payload、超限数字、模型/Tool 数据提高 budget 的拒绝测试。
- Eval/manual：不适用；没有真实模型调用或 CLI 用户路径。

## 15. Documentation impact

- [x] Engineering source of truth (`docs/`)：本 Spec、ADR-0009、Plan 与索引草案。
- [x] Site beginner learning path：解释 reducer、有界 Runtime 与 P1/P2 边界。
- [x] Site developer documentation：提供 F-0002 代码地图、失败语义与测试证据。
- [x] Site current status / milestone summary：F-0002 标记已实现；P1 尚未关闭。
- [x] Architecture / ADR：同步 Event 清单、预算当前事实与 accepted ADR-0009。
- [x] Deployment docs：无部署、migration 或运行入口变化。
- [x] Generated reference：公共 domain schema snapshot 已更新，并提供生成脚本。

## 16. Open questions

None. 项目所有者于 2026-08-11 接受本 Spec 与 ADR-0009。
