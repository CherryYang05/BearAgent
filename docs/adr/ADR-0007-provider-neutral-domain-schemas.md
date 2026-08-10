---
title: "ADR-0007: Provider-neutral domain schemas"
status: accepted
date: 2026-08-10
---

# ADR-0007：Provider 无关的领域 schema

## Context

P1 的 Run、EventStore、ModelProvider、Tool 和 CLI 需要共享 ID、Message、Error 与 Event
envelope。继续使用字符串、任意字典或外部 SDK 类型会使 adapter 细节泄漏到 runtime，并让
持久化 schema、兼容性测试和错误安全边界无法稳定。

这些类型是跨模块契约，且引入新的生产依赖，属于 S2 变更。

## Decision

- 使用 Pydantic v2 定义 Provider 无关的内部领域 schema；model 冻结、拒绝未知字段，并提供
  JSON schema 和 JSON 序列化。
- 核心 ID 使用 UUID4 的不透明 `RootModel` 类型。生产创建通过可注入的 `IdGenerator`，领域
  逻辑不得依赖 ID 的文本结构或排序。
- Message 使用带 discriminator 的 `text/tool_call/tool_result` part；P1 不引入多模态内容。
- Error 使用稳定 category/code/retryable 和受限安全详情。原始异常、堆栈和认证数据不属于
  可序列化错误契约。
- Event envelope 使用类型化 ID、正整数 sequence/schema version、带时区时间和 JSON-only
  payload。具体 Event payload 与数据库 schema 由后续 Feature 定义。
- 提交公共领域 model 的 JSON schema snapshot；有意变化必须显式更新 snapshot 并审查兼容性。

Pydantic 是内部 schema 库，不改变依赖方向：domain/ports 仍不得 import Provider SDK、CLI、
数据库 adapter 或其他外层类型。

## Alternatives

- 只用 dataclass 和手写校验/JSON schema：可保持标准库，但会重复实现 discriminated union、
  JSON-only 校验和 schema 生成，兼容性证据更弱。
- 使用普通字符串和字典直到 SQLite/Provider Feature：初期快，但会把歧义传播到每个端口，
  后续迁移面更大。
- 直接使用第一个 Provider SDK 的 message/response 类型：减少 adapter 翻译，但破坏可替换
  adapter 和稳定 domain 的架构边界。
- 使用 UUID7/ULID：可排序，但 Python 3.12 标准库不原生生成；P1 没有按 ID 时间排序的需求，
  不值得增加依赖或自定义实现。

## Consequences

- P1 增加一个明确的生产依赖和一组需要维护的 schema snapshot。
- adapter 必须显式翻译外部对象；Provider 新字段不会自动渗入 runtime。
- UUID4 不按时间排序；排序必须使用显式 sequence 或 occurred_at。
- schema 更严格，旧的 P0 字符串测试构造需要一次性迁移。
