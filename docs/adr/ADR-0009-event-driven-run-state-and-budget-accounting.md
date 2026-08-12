---
title: "ADR-0009: Compute Run state and budget usage from Events"
status: accepted
date: 2026-08-11
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0009：Run 状态和预算都从 Event 计算

## 要解决的问题

Agent Loop、SQLite 查询状态和 `run inspect` 都需要知道 Run 做到哪里、还剩多少预算。如果 Loop
维护一套可变计数，数据库再维护一套状态，CLI 从日志文本推断第三套结果，异常后就可能互相矛盾。

F-0003 尚未建立持久 schema，此时统一状态和记账规则不需要迁移已有 Run 数据。

## 比较过的方案

1. **Loop 直接修改 Run 对象。** 写起来最短，但 Store 和 CLI 必须复制规则，崩溃后也无法确认
   内存变化是否已经成为事实。
2. **类型明确的 Event + 纯 Reducer + 独立预算检查。** 需要更多 payload 和测试，但所有入口使用
   同一批事实和规则。
3. **任意字典 Event + 宽松 Reducer。** 文件少，但拼写错误、未知版本和关键 Event 可能被静默忽略。

## 决定

选择方案 2：

- `RunState` 和 `ActivityState` 是冻结的 BearAgent 类型；
- P1 Run 只包含 `QUEUED/RUNNING/SUCCEEDED/FAILED`，Activity 只包含
  `PENDING/RUNNING/SUCCEEDED/FAILED`；
- 模型和工具 Activity 都依次记录 requested、started、completed/failed，P1 同时最多一个 active Activity；
- Reducer 只接受白名单类型和版本，并要求同一 Run、连续 sequence、合法转换和唯一 ID；
- 预算上限由 `RunCreated` 固定。模型和工具只能报告用量，不能提高上限；
- 模型次数和工具次数在 request Event 记账；实际 token 与费用在模型完成或失败时记账；
- token、费用和总时间是所有新 Activity 共用的门槛；模型和工具次数只限制各自类型；
- 已开始的 Activity 即使超时或造成实际用量超限，完成/失败 Event 仍然保留；预算只阻止下一次 Activity；
- 费用使用整数 micro-USD。F-0002 不预测 token/费用，也不提前加入 pause、Approval 或 `UNKNOWN`。

## 失败时会发生什么

sequence 缺口、跨 Run、未知类型/版本、重复 ID 和非法状态转换都会被拒绝，旧状态不变。预算拒绝
发生在新的 Activity Event 被接受之前；调用方随后记录 `RunFailed`。损坏的 Event 序列不会被
跳过或猜测修复。

## 带来的影响

Store、Loop、CLI 和未来恢复使用同一套状态含义。代价是新增一组 v1 payload 和 schema 快照，
增加 Event 时必须同步 Reducer 与兼容性测试。单次模型调用仍可能让实际 token/费用超过上限，
Runtime 必须诚实显示并阻止下一步。

## 怎样验证

单元测试覆盖全部合法与非法转换、连续 sequence、输入不可变和五类预算边界。同一 Event 序列
反复重放必须得到值相等的状态。契约测试比较 schema 快照，架构测试阻止 Runtime 导入外层 SDK、
Store adapter 或 CLI。
