---
title: BearAgent 架构概览
description: BearAgent 的分层、依赖方向和当前实现边界。
bearStatus: mixed
sourceRefs:
  - architecture/overview
  - ADR-0001
  - ADR-0002
  - F-0002
  - F-0003
---

BearAgent 将不可预测的模型决策放在一个有明确边界的运行时中。核心层只使用 BearAgent
自己的类型；模型 SDK、数据库、CLI 和未来的 HTTP API 都位于适配器（Adapter）或外部入口
（Interface）边界。

:::caution[内容状态：已接受架构，不等于全部实现]
当前已完成工程基线、F-0001 内部数据格式、F-0002 reducer/预算、F-0003 SQLite EventStore 与
F-0004 ModelProvider boundary。
下图其余模块仍展示 P1-P3 的目标分层。
:::

```mermaid
flowchart TB
    U[User] --> I[CLI / Future API]
    I --> A[Application commands]
    A --> R[Runtime core]
    R --> C[Context builder]
    R --> M[Model port]
    R --> P[Policy port]
    R --> T[Tool executor]
    R --> E[Event store]
    M --> MA[Provider adapter]
    T --> WA[Workspace tools]
    E --> SQ[SQLite adapter]
```

## 依赖方向

```text
interfaces -> application -> domain/runtime ports
adapters   --------------------^
```

外层实现依赖内层规则。运行时核心不导入模型服务 SDK、Starlight、数据库适配器、FastAPI
或 UI。外部对象必须在适配器边界翻译为内部类型。

## 架构先解决四件事

1. **过程可查**：每次模型和工具操作、预算、错误和输出文件都能关联起来。
2. **恢复有依据**：已确认的操作不重复，无法确认的操作明确停住。
3. **权限在模型之外**：模型只能提出请求，运行时负责允许、询问或拒绝。
4. **数据由用户掌握**：第一版使用单用户、单进程、SQLite 和命令行，复杂度按真实需求增加。

Trace/replay/eval 是这些主线的验证面；Context、Skill、MCP 与 Memory 后置到 P4。下一步可以阅读
[产品定位](../project/positioning.md)、[F-0001：为什么先统一内部数据格式](domain-contracts.md)或
[持久事实与安全恢复的边界](../learn/durable-events.md)。
