---
title: "ADR-0001: Python and single-process first"
status: accepted
date: 2026-08-09
---

# ADR-0001：Python 与单进程优先

## Context

项目由个人开发，需要快速形成可用闭环，同时保留对 Agent runtime、tool、recovery 和 eval 的直接控制。

## Decision

P0-P3 使用固定版本 Python、一个 API/runtime 进程和 asyncio。CLI/API 共享同一 application/runtime；不引入分布式 queue 或独立 workflow service。

## Alternatives

- TypeScript/Bun：适合桌面/Web 一体，但本项目早期核心不是 UI，且 Python 模型/评测生态更直接。
- Rust/Go：运行时属性好，但会把大量早期时间投入 SDK、schema 和 Web 外围。
- Temporal/Celery：支持复杂分布式工作流，但单用户阶段增加部署、状态映射和调试成本。

## Consequences

- 交付快、测试和模型生态成熟；单进程的并发和隔离上限可接受。
- 必须通过端口和 adapter 控制 Python 动态性，使用 Pyright/Pydantic/contract tests。
- 出现多 worker、长 timer 或 SQLite 写竞争的真实证据后重新评估。
