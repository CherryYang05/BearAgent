---
title: "ADR-0003: SQLite as the initial durable store"
status: accepted
date: 2026-08-09
last_updated: 2026-08-12
---

# ADR-0003：SQLite 作为初始 durable store

## Context

项目需要事务性 Event append、projection、migration 和简单备份，但初期只有单用户单进程。
F-0003 开始前，Event/reducer 已成为稳定的内部数据规则，现在必须确定 SQLite 事务、数据迁移、
concurrency 和 adapter 边界，否则 Store、Loop 与 inspect 会各自形成不兼容的数据模型。

## Decision drivers

- 可维护性：保留显式 SQL 和少量标准库代码，不让 ORM model 成为第二套领域对象。
- 恢复语义：Event 是事实；projection 与 Event 同 transaction，Checkpoint 仍是后续可删优化。
- 安全：固定 SQL、绑定参数、有界 payload/query、安全错误；数据库内容仍作为不可信输入解析。
- 复杂度/交付时间：P1 单进程短事务，不引入连接池、writer service 或数据库依赖。
- 兼容与迁移：发布的 migration 按 hash 校验且不可编辑，schema 只前向递增。

## Decision

使用 SQLite WAL、显式 SQL migration 和轻量 async adapter。Event append 与 projection 更新在同一
transaction；大 Artifact 放文件系统并记录 hash/metadata。

F-0003 进一步固定：

- 使用 Python 标准库 `sqlite3`；async port 通过 `asyncio.to_thread` 执行有界短操作，不增加 ORM、
  `aiosqlite` 或连接池。
- 每个写操作使用独立 connection 与 `BEGIN IMMEDIATE`；SQLite 负责串行化 P1 单进程中的竞争
  writer，超过有限 `busy_timeout` 后安全失败，adapter 不无限重试。
- append transaction 读取并验证当前 projection/Event sequence，运行 F-0002 reducer，插入不可变
  Event，再 upsert Run 与变化的 Activity projection；任一步失败全部回滚。
- Event 表禁止 update/delete API。Run/Activity 表是可由 Event 重建的 projection，不可由调用方
  绕过 reducer 直接写入。
- schema 使用递增 SQL migration；ledger 记录 version、name 与 SHA-256。已应用 migration 的内容
  漂移、未来 version 或部分 schema fail closed。
- 初始化显式设置并验证 WAL、foreign keys、durable synchronous mode 与 busy timeout；普通 query
  不隐式创建或升级数据库。
- adapter 只向内层暴露 `Event`、`RunState` 和安全 Store errors，不暴露 `sqlite3.Connection/Row`。
- SQLite 文件不保存大 Artifact 内容；后续 Feature 只保存 Artifact metadata/hash，并由文件系统
  管理内容。

## Alternatives

- 纯 JSON/JSONL：可读但跨文件原子性、索引和 migration 成本更高。
- PostgreSQL：成熟但为个人本地运行引入额外服务和运维。
- ORM-first：开发方便，但容易让数据库模型泄漏到领域层并隐藏关键 transaction。

## Consequences

- local-first 和服务器单实例部署简单；SQLite FTS5 可覆盖早期检索。
- 先限定单 writer/process；出现真实写竞争、多实例或租户需求后再设计 PostgreSQL migration。
- thread cancellation 不能撤销已经进入 worker thread 的 transaction；P1 只承诺短、有界操作，不
  声称 cancel/resume 语义。
- normalized projection 增加 schema 和映射测试，但使 F-0005 inspect 无需重放全流或理解 SQL。

## Migration and rollback

F-0003 前不存在生产 Run 数据，从空数据库应用 schema v1。进入 main 后 migration v1 不可修改；
后续变化新增 migration 与兼容读取。Feature 合并前可以删除测试数据库并整体回退；合并后回退代码
必须识别现存 schema，数据 rollback 依赖备份或新 migration，不能改写历史 SQL。

## Validation

- 内存版/SQLite 版共用同一套接口测试，证明内部接口的行为不由某个适配器决定；
- 重开数据库验证 Event/projection durability 与 reducer 值等价；
- trigger/failure injection 验证 Event insert 后 projection failure 整体回滚；
- 并发相同 sequence 验证最多一个 writer 提交；
- migration version/hash、malformed JSON、projection drift、lock timeout 和 payload/query limits 测试；
- wheel 检查 migration SQL 被打包，架构测试阻止 core import SQLite adapter。

若出现多 Runtime process、持续 lock timeout、需要服务器横向扩展或数据库超出可接受大小的实际
证据，再评估专用 writer、connection strategy 或 PostgreSQL；不因 Roadmap 设想提前引入。
