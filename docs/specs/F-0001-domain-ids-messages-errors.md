---
title: "Feature: Domain IDs, messages and errors"
status: implemented
spec_id: F-0001
milestone: P1
owner: CherryYang05
created: 2026-08-10
last_updated: 2026-08-10
implemented_in: "PR #2"
related_adrs:
  - ADR-0001
  - ADR-0002
  - ADR-0007
---

# Feature: Domain IDs, messages and errors

## 1. Background / Problem

P0 提供的 `str` ID、字符串消息和最小 Event 只用于测试底座。P1 后续的 Run、
ModelProvider、EventStore、Tool 和 CLI 如果继续各自定义字符串与字典，会产生不可兼容的
跨模块契约，也无法稳定生成 JSON schema 或阻止 Provider 类型泄漏。

## 2. Goals

- G-1：为 P1 核心领域实体提供不透明、类型化且可注入生成器的 UUID4 ID。
- G-2：定义只包含文本、工具调用和工具结果，且不依赖特定模型服务商的 Message。
- G-3：定义稳定、可安全展示的错误分类、错误码和错误信息结构。
- G-4：补全版本化 Event envelope 的通用字段，并保持 Event 不可变。
- G-5：为公共内部数据格式建立 JSON Schema 快照与兼容性基线。

## 3. Non-goals

- NG-1：不实现 Run reducer、状态转换或预算执行。
- NG-2：不实现 SQLite、migration、projection 或恢复。
- NG-3：不实现真实 ModelProvider、ToolRegistry、文件工具或 CLI Run。
- NG-4：不支持图片、音频或其他多模态消息。
- NG-5：不定义具体 Event payload；具体 Event 与 projection 由后续 Feature 扩展。

## 4. Terms and assumptions

- ID 是不透明值；调用方不得依赖 UUID 文本中的时间、排序或其他业务含义。
- “安全错误信息”是允许进入 CLI、Event 和日志的摘要，不包含原始异常、堆栈、凭证或
  完整敏感输入。
- P1 Message 只覆盖文本 Agent Loop 所需的文本、工具调用和工具结果。

## 5. User scenarios

### Scenario A：跨模块关联

Given application 创建一个 Run，When EventStore、ModelProvider 和 CLI 传递其标识，Then
它们使用同一个 `RunId` 领域类型而不是各自定义的字符串或 SDK 类型。

### Scenario B：不依赖特定模型服务商的消息

Given assistant 请求一次工具调用，When adapter 翻译该响应，Then runtime 只接收 BearAgent
定义的 Message part，且可以用 `ToolCallId` 将结果关联回请求。

### Scenario C：安全错误输出

Given 外部边界返回异常，When application 构造可展示错误，Then只保留稳定错误码、分类、
可重试标志和经过筛选的安全上下文，不暴露原始异常或 secret 字段。

## 6. Functional requirements

- FR-1：至少定义 `SessionId`、`RunId`、`ActivityId`、`EventId`、`ArtifactId`、
  `ModelCallId`、`ToolCallId`、`CausationId` 和 `CorrelationId`。
- FR-2：ID 只能保存 UUID4；生产代码通过可替换的 `IdGenerator` 创建 ID。
- FR-3：Message role 只允许 `system/user/assistant/tool`。
- FR-4：Message part 使用带 discriminator 的 `text/tool_call/tool_result` 内部 schema。
- FR-5：system/user 只允许文本；assistant 允许文本或工具调用；tool 只允许工具结果。
- FR-6：错误分类至少覆盖 validation、budget、provider、tool、persistence、internal。
- FR-7：错误详情拒绝常见 secret/authorization 字段名，并限制展示文本与详情大小。
- FR-8：Event envelope 包含架构基线要求的 ID、sequence、event type、schema version、
  occurred time、causation、correlation 和 JSON payload。
- FR-9：所有公共领域 model 拒绝未知字段，实例冻结，并能序列化为 JSON 基础类型。

## 7. Interfaces

本 Feature 新增或冻结以下内部 Python 契约：

```text
domain.ids: opaque ID types + IdGenerator
domain.messages: MessageRole + Message + Message parts
domain.errors: ErrorCategory + ErrorCode + ErrorInfo + BearAgentError
domain.events: versioned Event envelope
```

这些类型是内部跨端口契约，不承诺作为独立第三方 Python SDK 的公开 API。

## 8. State and data model

- ID 的 JSON 形式是规范化的小写连字符 UUID 字符串。
- Event `sequence` 从 1 开始；`schema_version` 从 1 开始。
- `occurred_at` 必须包含时区并在序列化时规范化为 UTC。
- Event payload 只能包含 JSON 值；Pydantic/Provider/数据库对象不得进入 payload。
- F-0003 负责 SQLite 列类型、索引、transaction 和 migration。

## 9. Failure and recovery semantics

- 非 UUID4、空 Message、非法 role/part 组合、无时区时间和非 JSON payload 在构造边界失败。
- 领域校验失败不会自动重试。
- `BearAgentError` 的字符串形式只输出 `ErrorInfo.message`；原始异常只能作为 Python
  exception cause 存在，不进入序列化领域数据。
- 本 Feature 不提供 crash recovery。

## 10. Security and privacy

- Message、Event payload 和错误详情均视为不可信输入并执行结构校验。
- Error details 拒绝 `authorization`、`cookie`、`password`、`secret`、`token`、
  `api_key` 等敏感字段名。
- 内部数据格式不包含模型服务 SDK 响应、认证请求头或原始异常字段。
- 结构限制只减少意外泄露；调用方仍不得把 secret 放入安全 message 文本。

## 11. Observability

- Event envelope 的 `run_id`、`correlation_id`、`causation_id` 和 sequence 为后续结构化日志与
  Activity 检查提供关联字段。
- 错误包含稳定 category/code/retryable，后续可以聚合而不解析自由文本。

## 12. Rollout and rollback

- 一次性替换 P0 测试契约；P0 明确不承诺这些内部类型兼容。
- 暂无持久数据库，因此回退只需回退代码和 lockfile，不涉及数据 migration。
- F-0003 冻结持久化 schema 后，Event envelope 的变更必须增加 schema version/upcaster。

## 13. Acceptance criteria

- AC-1：每种 ID 可由 UUID4 创建、JSON 序列化和按具体类型比较；非法或非 UUID4 输入失败。
- AC-2：合法的文本、工具调用和工具结果 Message 可 JSON round-trip，非法 role/part 组合失败。
- AC-3：ErrorInfo 提供稳定分类、错误码和 retryable；敏感详情键、未知字段和超限内容失败。
- AC-4：Event envelope 包含全部通用字段，拒绝非法 sequence、无时区时间和非 JSON payload。
- AC-5：领域模块不 import Provider SDK、Typer、SQLite 或 adapter。
- AC-6：ID、Message、ErrorInfo 和 Event 的 JSON schema 与已提交 snapshot 一致。
- AC-7：受影响的 P0 fake model/store 与 ports 迁移到新的领域类型，现有行为测试继续通过。

## 14. Test plan

- Unit：ID 生成/解析、消息组合、错误限制、Event 验证和 JSON round-trip。
- Contract：公共 JSON schema snapshot/compatibility。
- Integration：P0 fake model/store 使用新领域类型。
- Recovery：不适用；没有持久存储或恢复行为。
- Security：敏感错误详情键、未知字段、非 JSON payload 和 Provider 类型泄漏检查。
- Eval/manual：不适用；没有真实模型行为。

## 15. Documentation impact

- [x] Architecture
- [x] ADR
- [ ] User docs
- [ ] Deployment docs
- [x] Generated reference

## 16. Open questions

None. P1 kickoff 已确认 UUID4、消息范围和错误安全边界。
