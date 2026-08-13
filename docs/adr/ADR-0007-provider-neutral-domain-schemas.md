---
title: "ADR-0007: Internal data formats independent of model providers"
status: accepted
date: 2026-08-10
---

# ADR-0007：不依赖特定模型服务商的内部数据格式

## Context

P1 的 Run、EventStore、ModelProvider、Tool 和 CLI 需要共享 ID、Message、Error 与 Event
通用外壳。继续使用字符串、任意字典或外部 SDK 类型会使适配器细节泄漏到运行时，并让
持久化数据格式、兼容性测试和错误安全边界无法稳定。

这些类型是跨模块统一使用的数据格式与规则，且引入新的生产依赖，属于 S2 变更。

## Decision

- 使用 Pydantic v2 定义不依赖特定模型服务商的内部数据模型；模型冻结、拒绝未知字段，并提供
  JSON Schema 和 JSON 序列化。
- 核心 ID 使用 UUID4 的不透明 `RootModel` 类型。生产创建通过可注入的 `IdGenerator`，领域
  逻辑不得依赖 ID 的文本结构或排序。
- Message 用类型标识字段区分 `text/tool_call/tool_result` 内容块；P1 不引入多模态内容。
- Error 使用稳定的类别、代码、“是否可重试”标志和受限安全详情。原始异常、堆栈和认证数据不属于
  可序列化错误数据。
- Event 通用外壳使用类型化 ID、正整数顺序号和数据格式版本、带时区时间及只含 JSON 的
  数据。具体 Event 数据与数据库格式由后续 Feature 定义。
- 提交公共内部数据模型的 JSON Schema 快照；有意变化必须显式更新快照并审查兼容性。

Pydantic 是内部数据校验库，不改变依赖方向：`domain/ports` 仍不得导入模型服务 SDK、CLI、
数据库适配器或其他外层类型。

## Alternatives

- 只用 dataclass 和手写校验/JSON Schema：可保持标准库，但会重复实现带类型标识的联合结构、
  纯 JSON 校验和数据格式生成，兼容性证据更弱。
- 使用普通字符串和字典直到 SQLite 或模型服务 Feature：初期快，但会把歧义传播到每个内部接口，
  后续迁移面更大。
- 直接使用第一个模型服务 SDK 的消息和响应类型：减少适配器翻译，但破坏可替换
  适配器和稳定内部数据模型的架构边界。
- 使用 UUID7/ULID：可排序，但 Python 3.12 标准库不原生生成；P1 没有按 ID 时间排序的需求，
  不值得增加依赖或自定义实现。

## Consequences

- P1 增加一个明确的生产依赖和一组需要维护的 JSON Schema 快照。
- 适配器必须显式翻译外部对象；模型服务商的新字段不会自动渗入运行时。
- UUID4 不按时间排序；排序必须使用显式 sequence 或 occurred_at。
- 内部数据格式更严格，旧的 P0 字符串测试构造需要一次性迁移。
