---
title: F-0001：为什么先建立领域契约
description: 通过稳定 ID、Message、Error 和 Event envelope 隔离 Runtime 与外部 SDK。
bearStatus: implemented
sourceRefs:
  - F-0001
  - ADR-0007
---

F-0001 是 BearAgent 在 P1 完成的第一个 Feature。它没有实现 Agent Loop，而是先回答一个更基础的
问题：后续模块之间用什么语言交流？

:::tip[内容状态：当前已实现]
本页描述的 ID、Message、Error 和通用 Event envelope 已有代码、测试与 schema snapshot。
真实 Provider、Tool 和 SQLite 仍未实现。
:::

## 为什么不能继续传字符串和字典

如果 CLI、Runtime、Provider 和 EventStore 都自行定义 `run_id`、消息和错误结构，同一个概念会
逐渐出现不同字段、不同限制和不同 JSON 形式。Provider SDK 的响应类型也可能渗透进 Runtime，
让更换模型或持久化旧事件变得困难。

F-0001 因此建立四组 Provider 无关契约。

## 1. 不透明 ID

`SessionId`、`RunId`、`ActivityId`、`EventId` 等 ID 是不同类型的 UUID4。代码不能因为它们最终
序列化为字符串，就把 Run ID 误传到 Activity ID 的位置，也不能依赖 UUID 文本进行业务排序。

## 2. Message

Message 明确区分 `system`、`user`、`assistant` 和 `tool` role，并使用带 discriminator 的
`text`、`tool_call`、`tool_result` part。Provider Adapter 以后负责把外部 SDK 对象翻译进来。

## 3. 安全 Error

错误包含稳定的 category、code 和 retryable 标志。可序列化详情拒绝常见 secret 字段并限制
大小；原始异常与堆栈不能直接进入面向用户的领域错误。

## 4. Event envelope

Event 具有 `event_id`、`run_id`、sequence、schema version、带时区时间、causation、correlation
和 JSON payload。它提供后续 EventStore 的通用外壳，但具体 Run 事件仍由后续 Feature 定义。

## 这对后续架构有什么价值

```mermaid
flowchart LR
    SDK[Provider SDK object] --> AD[Provider adapter]
    AD --> MSG[BearAgent Message]
    MSG --> RT[Runtime core]
    RT --> EVT[BearAgent Event]
    EVT --> SA[Storage adapter]
```

外部格式可以变化，但 Runtime 中间的语言保持稳定。这样才能为 Provider contract、EventStore、
Tool 和 CLI 分别添加实现，而不让某一个外部框架主导整个领域模型。

## 从哪里看代码

- 领域实现：`src/bearagent/domain/`
- Schema snapshot：`tests/snapshots/domain_schemas.json`
- 单元与安全测试：`tests/unit/`、`tests/security/`
- 工程需求：`docs/specs/F-0001-domain-ids-messages-errors.md`
- 设计理由：`docs/adr/ADR-0007-provider-neutral-domain-schemas.md`
