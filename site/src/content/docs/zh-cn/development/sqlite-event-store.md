---
title: F-0003 SQLite EventStore 实现导读
description: EventStore port、SQLite migration、transaction、projection 与故障测试代码地图。
bearStatus: implemented
sourceRefs:
  - F-0003
  - ADR-0003
  - PLAN-F-0003
---

F-0003 把 F-0002 的纯状态语义接到第一个生产持久化 adapter，同时保持依赖方向：core 不 import
SQLite，adapter 只返回 BearAgent 的 `Event` 与 `RunState`。

## 代码地图

| 入口 | 责任 |
|---|---|
| `src/bearagent/ports/store.py` | append/list/get_run contract、bounded query、安全错误 |
| `src/bearagent/adapters/testing/store.py` | 与 SQLite 共用 contract 的确定性内存 adapter |
| `src/bearagent/adapters/sqlite/store.py` | initialization、serialization、transaction 与 projection 映射 |
| `src/bearagent/adapters/sqlite/migrations/0001_initial.sql` | Event/Run/Activity/schema ledger v1 |
| `tests/contract/test_event_store_contract.py` | 两种 adapter 的共同可观察行为 |
| `tests/integration/test_sqlite_event_store.py` | WAL/reopen、migration、并发、rollback、corruption |
| `tests/security/test_sqlite_event_store.py` | 固定 SQL、内容/路径不泄漏、锁超时和资源上限 |

## 关键边界

- 使用标准库 `sqlite3` + `asyncio.to_thread`，没有新增生产依赖或 ORM model。
- append 使用独立 connection 和 `BEGIN IMMEDIATE`；有限 busy timeout 后返回 retryable safe error。
- Event payload 以 deterministic compact JSON 保存，读取时重新经过 Event 与 typed payload validation。
- schema migration ledger 校验 version、name 和 SHA-256；已发布 migration 不能原地改写。
- projection failure trigger 测试证明 Event insert 与 projection update 同时回滚。
- adapter 不提供 Event update/delete 或直接写 projection 的 API。

## 验证重点

共享 contract 避免 InMemory 与 SQLite 对合法 Event 各说各话；重开数据库后 projection 必须与
`reduce_events` 值相等。并发测试让两个 writer 请求同一个 sequence，只允许一个状态提交；损坏
测试直接修改数据库 JSON/sequence，要求读取 fail closed。

F-0003 没有 startup recovery。看到非终态 projection 只说明事实仍在，不代表 Runtime 已经知道如何
安全继续；继续执行、Checkpoint 和 `UNKNOWN` 处置属于 P2。
