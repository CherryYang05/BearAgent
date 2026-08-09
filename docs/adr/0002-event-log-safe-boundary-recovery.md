---
title: "ADR-0002: Event log and safe-boundary recovery"
status: accepted
date: 2026-08-09
---

# ADR-0002：Event log 与安全边界恢复

## Context

长任务会在模型调用、工具副作用和审批中断。只保存聊天消息无法解释状态，也无法安全恢复。

## Decision

不可变 Event 是运行事实来源；Run/Activity/Approval 表是事务更新的 projection；Checkpoint 是可删除重建的优化。只在持久化 Activity 边界恢复，不序列化协程或任意调用栈。

不能确认外部副作用是否提交时，Activity 进入 `UNKNOWN`。只有纯读或有幂等键/receipt 的操作可以自动重试。

## Alternatives

- 只保存最终 message/JSONL：实现快，但状态查询、迁移和并发一致性弱。
- 保存完整 Python object/coroutine：与代码版本耦合，难迁移且不能可靠处理外部副作用。
- 一开始接入通用 durable workflow engine：能力强，但会掩盖需要学习和定义的 Agent 语义。

## Consequences

- schema/version/reducer 测试成为核心工作；写路径比普通 chat demo 更复杂。
- 获得可恢复、可审计、可导出 eval trace 的统一基础。
