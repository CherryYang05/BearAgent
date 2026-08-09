---
title: "ADR-0003: SQLite as the initial durable store"
status: accepted
date: 2026-08-09
---

# ADR-0003：SQLite 作为初始 durable store

## Context

项目需要事务性 event append、projection、migration 和简单备份，但初期只有单用户单进程。

## Decision

使用 SQLite WAL、显式 SQL migration 和轻量 async adapter。Event append 与 projection 更新在同一 transaction；大 Artifact 放文件系统并记录 hash/metadata。

## Alternatives

- 纯 JSON/JSONL：可读但跨文件原子性、索引和 migration 成本更高。
- PostgreSQL：成熟但为个人本地运行引入额外服务和运维。
- ORM-first：开发方便，但容易让数据库模型泄漏到领域层并隐藏关键 transaction。

## Consequences

- local-first 和服务器单实例部署简单；SQLite FTS5 可覆盖早期检索。
- 先限定单 writer/process；出现真实写竞争、多实例或租户需求后再设计 PostgreSQL migration。
