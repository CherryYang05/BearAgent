---
title: "Feature: Run reducer, Activity lifecycle and budgets"
status: implemented
spec_id: F-0002
milestone: P1
owner: CherryYang05
created: 2026-08-11
last_updated: 2026-08-13
implemented_in: "PR #5"
related_adrs:
  - ADR-0001
  - ADR-0002
  - ADR-0007
  - ADR-0009
---

# F-0002：从 Event 计算 Run/Activity 状态和预算

## 1. 为什么现在要做

F-0001 规定了 Event 的通用字段，但还不能表示“模型调用已经开始”“Tool 已经完成”或“Run 因预算
耗尽失败”。如果 Agent Loop、SQLite projection 和 `run inspect` 各自维护状态和计数，异常后可能
给出不同结论，预算也可能在某个入口被漏掉。

F-0002 把这些规则集中在无 I/O 的 Reducer 中。同一串有序 Event 必须得到值相等的 `RunState`；
每个新的模型或 Tool Activity 在成为 Event 前都要经过同一套预算检查。

## 2. 本次交付

- G-1：P1 Run 和 Activity 的状态以及不可变状态对象；
- G-2：描述状态变化的 12 种版本化 Event payload；
- G-3：逐条验证 Event 并返回新状态的纯 Reducer；
- G-4：模型次数、Tool 次数、token、费用和总时间的统一记账；
- G-5：预算耗尽和非法 Event 返回稳定、安全的 Error，不继续调度；
- G-6：新增数据类型进入 JSON schema 快照。

## 3. 本次不做

不调用模型或 Tool，不实现 Agent Loop、CLI Run、SQLite 和 transaction。不包含 pause/resume/cancel、
Attempt、Receipt、Checkpoint、启动恢复或 `UNKNOWN`；这些属于 P2。不包含 Grant、Approval 和
sandbox；这些属于 P3。不引入并行 Activity、多个 Agent 或新生产依赖。

已经开始的外部调用不会被本 Feature 强制取消。token 和费用也不在调用前预测。

## 4. 需要先说明的约定

- 一次被接受的 `ModelCallRequested` 计为一次模型调用；
- 一次被接受的 `ToolCallRequested` 计为一次 Tool 调用；
- token 和费用只根据模型完成/失败 Event 中报告的实际 usage 累加；
- 费用用非负整数 micro-USD 保存，避免浮点比较；
- 总时间从 `RunStarted` 到候选新 Activity 的 UTC 时间差计算；
- `PENDING` 或 `RUNNING` 的 Activity 为 active，P1 同时最多一个；
- sequence 决定事实顺序，时间戳只用于时间预算和检查。

五类上限都允许为 0，以支持“创建后立即耗尽”的确定性测试；负数、布尔值和无界大整数被拒绝。

## 5. 使用场景

### 同一批事实得到同一状态

内存执行路径、未来 SQLite projection 和测试重放同一串连续 Event 时，应得到值相等的 Run 状态、
Activity 列表和预算用量。

### 非法 Event 不改变旧状态

终态后追加 Event、重复 Activity ID、sequence 缺口、跨 Run Event 或错误的完成 Event 都被拒绝，
传入的旧状态保持不变。

### 预算在下一次调用之前把关

当模型次数或 Tool 次数已经达到上限，或者 token、费用、总时间已经耗尽，Runtime 准备请求下一次
Activity 时收到 `budget_exhausted`。该请求不会进入 Event 序列；调用方随后记录 `RunFailed`。

### 已经发生的超额用量仍被记录

Activity 在 deadline 前通过检查并开始，后来跨过 deadline 或让实际 token/费用超限。完成或失败
Event 仍被接受并如实记账，只有后续新 Activity 被阻止。

## 6. 必须满足的行为

- FR-1：P1 `RunStatus` 只有 `QUEUED / RUNNING / SUCCEEDED / FAILED`，后两者为终态；
- FR-2：`ActivityStatus` 为 `PENDING / RUNNING / SUCCEEDED / FAILED`，kind 为 `MODEL / TOOL`；
- FR-3：支持 RunCreated、RunStarted、ModelCallRequested/Started/Completed/Failed、
  ToolCallRequested/Started/Completed/Failed、RunSucceeded、RunFailed；
- FR-4：每个 `event_type + schema_version` 对应精确 Pydantic payload，未知组合被拒绝；
- FR-5：首条 Event 必须是 sequence 1 的 RunCreated，后续必须同 Run、连续并符合状态转换；
- FR-6：request 创建 PENDING，started 转为 RUNNING，completed/failed 转为对应终态；各 ID 不可复用；
- FR-7：P1 最多一个 active Activity，存在 active Activity 时 Run 不能结束，Run 终态后不接收 Event；
- FR-8：RunState 保存 Run/Session ID、状态、预算、Activity、时间、终态 Error 和 last sequence；
- FR-9：预算字段至少包含模型次数、token、micro-USD、总毫秒数和 Tool 次数，均为安全范围内整数；
- FR-10：模型/Tool 次数在 request Event 增加，token/费用在模型完成或失败 Event 增加；
- FR-11：模型次数只检查新模型 Activity，Tool 次数只检查新 Tool Activity，其余三项对两者都生效；
- FR-12：次数按“当前用量 + 候选请求”判断；一次已开始模型调用可以造成实际 token/费用超限；
- FR-13：started、completed、failed 和 Run terminal Event 记录事实，不因 deadline 或超额被丢弃；
- FR-14：预算 Error 包含 dimension、limit、consumed、requested，code 为 `budget_exhausted`；
- FR-15：Reducer 和预算检查不读时钟、不做 I/O、不修改输入；候选 UTC 时间由调用方传入；
- FR-16：新增状态和 payload 进入公共 schema 快照，Runtime 不导入外层 SDK、CLI、SQLite 或 adapter。

## 7. 对外入口和模块连接

```text
domain.runs
  RunStatus / ActivityKind / ActivityStatus
  BudgetLimits / BudgetUsage / BudgetExhaustion
  ActivityState / RunState

domain.run_events
  12 种 v1 payload + type/version registry

runtime.reducer
  reduce_event(previous_state, event) -> RunState
  reduce_events(events) -> RunState

runtime.budgets
  check_activity_budget(state, activity_kind, occurred_at)
```

Agent Loop 以后负责决定何时构造候选 Event；Event store 负责保存；CLI 负责显示。三者直接调用这里的
状态和预算规则，不复制实现。

## 8. 状态和保存的数据

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

RunCreated 保存 Session ID 和全部预算上限。模型 Activity 使用 Activity ID + ModelCall ID，Tool
Activity 使用 Activity ID + ToolCall ID，并保存受限 tool name。模型完成或失败 payload 保存非负
input/output token 和 micro-USD。

失败 payload 只保存安全 `ErrorInfo`，不保存原始异常、堆栈或 SDK response。Reducer 返回新的冻结
状态，Activity 按请求顺序保存在不可变序列。数据库列和 migration 由 F-0003 决定。

## 9. 失败时会发生什么

sequence 不连续、跨 Run、未知类型/版本、重复 ID、非法转换和错误 payload 在 Reducer 入口失败，
不会留下部分状态。预算拒绝后，候选 Activity Event 不被接受；调用方使用连续 sequence 记录带
`BUDGET_EXHAUSTED` 的 RunFailed。

已开始 Activity 可以在 deadline 后完成或报告超额 usage。P1 不强制取消，也不扫描非终态 Run。
损坏 Event 序列不会被跳过或合成为成功。

## 10. 安全与隐私

Event payload、Error 和预算都按不可信数据校验，未知字段和不安全整数被拒绝。模型或 Tool 不能
发明 Event 改状态，也不能提高 RunCreated 中的限制。新增 payload 不保存认证头、密钥、SDK 对象
或完整敏感 Tool 输出。本 Feature 没有文件、网络、数据库或 shell 副作用。

## 11. 怎样检查执行过程

RunState 暴露 last sequence、Run/Activity 状态、预算上限/用量和安全终态 Error。每个 Activity
保存请求、开始、结束时间和类型化 ID，供后续 projection 和 inspect 使用。预算 Error 直接提供
维度和数字，不需要解析自由文本。

## 12. 上线与回退

当前没有持久 Run 数据，因此可以在 F-0003 前一次性增加状态、payload、Reducer 和快照。回退只需
删除新增模块并恢复 schema snapshot。SQLite v1 建立后，不兼容 payload 必须使用新版本和迁移。

## 13. 验收标准

- AC-1：合法 Run Event 可从无状态推进到 QUEUED、RUNNING 和一个终态，JSON 往返后值相等；
- AC-2：模型和 Tool Activity 按四个状态转换并关联正确 ID，不允许 active Activity 重叠；
- AC-3：sequence 缺口、跨 Run、重复 ID、未知类型/版本、终态后 Event 和非法转换稳定失败；
- AC-4：次数在 request 记账，token/费用在完成或失败记账，失败 Activity 的已知 usage 不丢失；
- AC-5：五类预算覆盖未耗尽、恰好耗尽和超限；拒绝后可生成安全 BUDGET_EXHAUSTED Error；
- AC-6：已开始 Activity 跨 deadline 或实际超额仍可完成/失败，后续请求被拒绝；
- AC-7：同一 Event 序列重复重放得到值相等状态，Reducer 不依赖时钟、随机数或 I/O；
- AC-8：新 schema 与快照一致，F-0001 schema 没有意外不兼容变化；
- AC-9：import boundary、Ruff、Pyright、pytest、文档检查和站点构建通过。

## 14. 验证方式

- Unit：全部合法/非法状态转换、冻结、ID 唯一、sequence/Run 一致和重放；
- Unit：五类预算边界、候选次数、实际超额和 deadline；
- Contract：状态、预算和 Event payload schema 快照；
- Recovery：只验证 Event fold 的确定性，不做进程重启；
- Security：未知类型/版本、恶意 payload、大整数和提高预算的请求；
- Integration/Eval：不适用，没有 store、真实模型或 CLI。

## 15. 文档同步

- [x] Engineering docs / Architecture / ADR
- [x] Site learning path
- [x] Site developer guide
- [x] Site status and milestones
- [x] Generated schema snapshot
- [x] Deployment impact checked: none

## 16. 尚未决定的问题

无。项目所有者于 2026-08-11 接受本 Spec 与 ADR-0009。
