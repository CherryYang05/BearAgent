---
title: "ADR-0003: Use SQLite for the first durable store"
status: accepted
date: 2026-08-09
last_updated: 2026-08-12
---

# ADR-0003：第一版使用 SQLite 保存执行记录

## 要解决的问题

BearAgent 需要在一次事务中追加 Event 并更新查询状态，还需要迁移、索引和简单备份。P1 至 P3
只有单用户和单进程，不需要为此运行独立数据库服务。

## 决定

使用 SQLite WAL、显式 SQL migration 和轻量 async adapter。追加 Event 与更新 projection 必须在
同一个 transaction 中完成。大 Artifact 放在文件系统，数据库只保存路径、hash 和元数据。

## 为什么不选其他方案

- JSON/JSONL 可读，但跨文件原子更新、索引和迁移更难；
- PostgreSQL 成熟，却为个人本地运行增加独立服务；
- ORM 可以减少样板代码，但容易让数据库模型进入领域层，并隐藏关键 transaction。

## 带来的影响

本地运行、单机部署和备份更简单。第一版限制单 writer/process。只有真实写竞争、多实例或多租户
需求出现后，才设计 PostgreSQL 迁移。

## 怎样验证

SQLite adapter 必须通过从空库迁移、Event 顺序、事务回滚、并发冲突和备份恢复测试；同一组 store
行为测试还要跑在内存实现上，确保调用方换实现时不用改变用法。
