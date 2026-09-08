---
title: "ADR-0020: read committed Events independently before making recovery decisions"
status: proposed
date: 2026-09-08
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0020：先独立读取 Event 重建状态，再接入恢复决定

关联 [F-0021](../specs/F-0021-event-replay-startup-check.md)。这是 P2 启动设计，尚未接受或实现。

## 为什么需要新的边界

P1 的 EventStore 查询会先验证 projection。这个行为能阻止调用方在缓存与 ledger 不一致时继续使用
已有写入路径，却不能在 projection 不可用时回答“Event 本身还记录了什么”。把查询校验直接移除，
又会改变已交付的存储契约，并容易让未来调度器错把只读重建当作恢复许可。

## 比较过的方案

| 方案 | 好处 | 代价与失败方式 |
|---|---|---|
| 放宽现有 get_run/list_events，发现坏 projection 就自动重建写回 | 用户入口少 | 查询隐含写入；修复与运行并发时可能覆盖更新，改变 P1 契约 |
| 单独读取 Event，在内存重建并报告 | 保留 P1 契约；容易验证零额外执行 | 新增只读 port，projection 修复需以后单独处理 |
| 先做 Checkpoint，再实现恢复 | 长历史可能更快 | 没有 Event-only 基准时无法验证缓存正确性，引入过早的持久格式 |
| 引入完整 workflow/checkpointer 框架 | 可以使用已有恢复设施 | 需要将 BearAgent Event、Policy、预算和 Tool 副作用重新映射，当前无必要 |

## 建议采用的决定

选择独立只读 `EventReplaySource`，保留现有 EventStore 契约。Reader 从 Event 枚举 Run，不借
projection 的状态筛选候选项。每个 Run 的 Event 边界与对照资料在同一 SQLite 读事务中捕获；核心
只接收 BearAgent 快照类型，不持有数据库连接。application 用现有 Reducer 和历史一致性校验重建。

一次重建要么返回受限范围内的完整状态，要么返回明确错误；不能以最后一页、部分 payload 或当前
配置补齐历史。state hash 必须带格式版本，只用于一致性比较。分页扫描可报告不同 Run 各自的快照，
不能伪装成整库同时刻视图，也不能按 UUID 大小解释执行先后。

P1 的 `RUNNING` 只说明终态事实尚未提交。只读检查不得推断调用没发生，也不得写入成功、失败、
`UNKNOWN` 或 RecoveryDecision。需要续跑时，F-0022 至 F-0024 仍须重新检查状态、预算、权限及副作用
证据；本次快照不能充当执行锁或授权。

## 资源、迁移与回退

按 Spec 约束 Event 条数、累计字节、Run 页大小和读取期限。SQLite 工作在线程内执行时，取消必须
落实到查询和连接生命周期，不能只取消等待者。单个坏 Run 要显式报告，不能隐藏为健康终态。

不改 Event v1-v4，不加 SQL migration，不写回 projection。支持读取已知格式中的 Event 与 migration，
即使 projection 的行或表缺失；ledger 本身损坏仍安全拒绝。回退只移除新增入口，原有 Event 和
projection 不需要恢复或转换。Checkpoint 以后有实测收益时再单独决定格式与 fallback。

## 怎样验证

同一组 contract tests 运行内存与 SQLite source；故障集覆盖 projection 删除/篡改、未知 schema、
Event 缺口、双连接追加和取消。复用 K1-K6 的子进程数据，断言重建状态和额外外部调用次数为零。
为代表性和上限历史记录 Event 数、总字节、耗时、环境和内存边界，作为是否需要 Checkpoint 的依据。

## 外部资料与适用范围

2026-09-08 核对的资料只用于方案比较，不能证明 BearAgent 已有这些行为：

- [SQLite isolation](https://www.sqlite.org/isolation.html) 说明 WAL 下读事务使用稳定快照；本设计据此把
  单 Run 的边界和数据放在同一个读事务中，不把多个独立分页连接当作同一快照。
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 区分 graph checkpoint
  与跨执行存储。本项目选择先验证 Event-only 基线，不引入其状态持久化模型。
- [LangGraph releases](https://github.com/langchain-ai/langgraph/releases) 当日可见持续发布记录，包括
  8 月的 langgraph 1.2.11 与 SDK 0.4.4；因此是仍维护的比较对象。活跃发布不代表恢复语义适合直接采用。
