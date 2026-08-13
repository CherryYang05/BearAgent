---
title: "ADR-0009: Event-driven Run state and budget accounting"
status: accepted
date: 2026-08-11
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0009: Event-driven Run state and budget accounting

## Context

F-0001 只固定了通用 Event envelope。F-0003 的持久 projection、F-0004 的 ModelProvider、F-0016 的 Agent Loop 与 F-0005
的 inspect 都需要共享 Run/Activity 状态和预算。如果 Loop 维护可变计数、Store 维护另一套状态、
CLI 再从日志文本推断，会产生无法解释的分叉，并让 budget check 在不同入口被绕过。

现在尚无持久 Run 数据，是在 SQLite schema 和真实 Provider 接入前固定状态事实、预算单位与非法
转换处理的最低迁移成本时点。

## Decision drivers

- 可维护性：状态转换只有一个无 I/O 的实现，外围只翻译输入和持久化结果。
- 恢复语义：完整 Event sequence 可确定性重建 state，为 P2 replay/checkpoint 提供基础。
- 安全：未知 Event、非法转换和模型要求提高预算必须 fail closed。
- 复杂度/交付时间：P1 保持串行 Activity，不引入 workflow engine 或并发状态组合。
- 兼容与迁移：F-0003 前冻结 v1 payload 与公共 schema，后续按版本演进。

## Considered options

### Option A：Agent Loop 持有可变 Run 对象和预算计数

实现最直接，但 EventStore projection 和 CLI 必须复制转换逻辑。崩溃或异常路径容易出现内存状态
已变、事实未记录，后续 replay 也无法证明与原执行一致。

### Option B：严格 typed Event + 纯 reducer + 独立预算 gate

每个状态变化由白名单、版本化 Event 表达；reducer 只接受连续合法转换并返回不可变新 state。
预算 gate 与 reducer 共用同一状态和规则，在 Activity request 前检查。代价是需要更多 payload、
转换和 schema 测试。

### Option C：通用字典 payload + 宽松 reducer

前期文件少，也更容易让未来 Event 被旧代码“忽略”。但拼写错误、未知版本或本应改变状态的事实
可能被静默吞掉，损坏 projection 仍看似正常，不适合作为 durable runtime 基础。

## Decision

选择 Option B，并限定如下：

- `RunState` 与 `ActivityState` 是冻结且不依赖模型服务、存储或外部入口的 Pydantic 内部数据模型。
- P1 只实现当前可达状态：Run 的 `QUEUED/RUNNING/SUCCEEDED/FAILED`，Activity 的
  `PENDING/RUNNING/SUCCEEDED/FAILED`。Pause、cancel、approval 和 `UNKNOWN` 由后续 Feature
  通过新 Event/状态显式增加，不提前声称可用。
- Model/Tool Activity 都使用 request -> started -> completed/failed 的显式 Event，P1 同时最多
  一个 active Activity。
- reducer 对 event type + schema version 使用显式 registry；sequence gap、跨 Run、未知类型/
  版本、重复 ID 和非法转换全部 fail closed，不跳过也不修猜测状态。
- budget limits 在 `RunCreated` 中成为受信事实；模型或 Tool 数据只能报告 usage，不能扩大 limits。
- 费用使用整数 micro-USD；model iteration 与 Tool call 在 request Event 记账，实际 token/费用在
  模型 completion/failure Event 记账。
- budget gate 只阻止新的 Activity request。模型次数只约束新的 Model Activity，Tool 次数只约束
  新的 Tool Activity；token、费用和 wall time 是全局门槛。
- 已开始的 Activity 即使跨过 deadline 或造成实际 token/费用超限，其 completion/failure 事实仍
  必须记录。F-0002 不丢事实，也不伪装成能够取消外部调用；超限后禁止下一个 Activity。
- terminal Event 可以记录已完成 Run；预算门不把已经生成的最终结果改写成不存在。
- F-0002 不做 token/费用预测。F-0004 可使用 Provider max-output 等能力减少单次超额，但不能改变
  “实际 usage 返回后记账”的事实语义。

## Consequences

### Positive

- Store projection、Loop、inspect 和未来 replay 共享一套可测试状态语义。
- 非法 Event stream 会在最早边界暴露，不会被宽松投影掩盖。
- 预算单位、记账点和单次实际超额的处理明确，可用确定性测试证明。
- P1 不需要数据库、网络、系统时钟或 workflow engine 就能完成核心验证。

### Negative / debt accepted

- 需要为 Model call 增加显式 started Event，并维护一组 v1 payload/schema snapshot。
- token/费用只能在 Provider 返回 usage 后精确记账，单次调用可能超过 limit；F-0004 必须在用户
  文档和 inspect 中诚实展示这一限制。
- strict registry 意味着新增状态相关 Event 时必须同时更新 reducer 与兼容性测试。
- P1 串行 Activity 限制吞吐，但避免在恢复和权限语义稳定前引入组合状态。

## Migration and rollback

当前不存在持久 Run/Event 数据。接受后一次性新增内部数据模型、事件数据、reducer 和快照；回退
只需删除新增模块并恢复文档/schema snapshot。F-0003 建立 SQLite v1 后，任何不兼容 payload
变化必须使用新 schema version/upcaster 和 migration 说明，不能原地改义。

## Validation

- unit tests 覆盖所有合法/非法 Run 与 Activity 转换、sequence/run 一致性和输入不可变性；
- budget tests 覆盖五类 limit、prospective count、deadline 与 completion 实际超额；
- replay tests 对同一 Event sequence 多次 fold 并比较完整 state；
- contract snapshot 覆盖新增领域/payload schema，同时防止 F-0001 schema 意外漂移；
- architecture test 继续阻止 core import Provider SDK、Store adapter、CLI 或框架。

当 P2 需要 checkpoint/attempt/`UNKNOWN`，或真实 P1 trace 证明单次 token/费用超额不可接受时，
重新评估 Event 集合和 reservation 机制；不能在 F-0002 中预设并行或分布式方案。
