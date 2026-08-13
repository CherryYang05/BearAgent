---
title: "ADR-0002: Events are execution facts and recovery resumes at saved boundaries"
status: accepted
date: 2026-08-09
---

# ADR-0002：Event 是执行事实，恢复只发生在已保存边界

## 要解决的问题

长任务可能在模型调用、文件写入或等待用户批准时中断。只保存聊天消息，无法知道某次工具调用
是否开始、是否完成，也无法判断重启后能否安全重试。

## 决定

不可变 Event 保存已经发生的事实。Run、Activity 和 Approval 表只提供查询结果，可以由 Event
重建；Checkpoint 只是加快重建的快照。Runtime 只在已持久化的 Activity 边界恢复，不保存 Python
协程或调用栈。

外部写入可能已发生、但结果无法确认时，Activity 进入 `UNKNOWN`。纯读操作，或具有幂等键、
Receipt 的写操作，才允许自动重试。

## 为什么不选其他方案

- 只保存最终消息或 JSONL，难以保证跨状态更新的一致性；
- 保存 Python 对象或协程会与代码版本绑定，也处理不了已经发生的外部副作用；
- 直接采用通用 durable workflow engine，会在 BearAgent 自己的恢复语义尚未明确时增加一层映射。

## 带来的影响

写路径需要维护 Event 版本、Reducer 和恢复测试，复杂度高于普通聊天 demo。得到的回报是：状态、
恢复决定、审计和评测 trace 可以建立在同一批事实上。
