---
title: "ADR-0001: P0-P3 use Python and one process"
status: accepted
date: 2026-08-09
---

# ADR-0001：P0–P3 使用 Python 和单进程

## 要解决的问题

BearAgent 由个人开发。早期需要直接接入模型和评测生态，也需要看清状态、恢复和权限规则。如果
同时引入多语言服务、任务队列和分布式 worker，部署与调试成本会先于用户价值出现。

## 决定

P0 至 P3 固定使用 Python 3.12、asyncio 和一个 API/Runtime 进程。CLI 和未来 API 调用同一套
application 与 Runtime 代码；不引入分布式队列或独立 workflow service。

## 比较过的方案

- TypeScript/Bun 更适合 Web 与桌面一体开发，但早期核心不是 UI；
- Rust/Go 的运行时特性更强，但模型 SDK、schema 和评测接入成本更高；
- Temporal/Celery 能处理复杂分布式流程，但单用户阶段会增加部署和状态映射。

## 带来的影响

Python 让早期交付和测试更直接。动态语言带来的边界风险通过类型检查、Pydantic、port 和契约测试
控制。单进程的吞吐和隔离上限是当前接受的代价。

## 何时重新评估

只有出现多 worker、跨天 timer 或 SQLite 写竞争的实际证据时，才重新评估语言或分布式执行方案。
