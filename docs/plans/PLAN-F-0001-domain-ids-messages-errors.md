---
title: "Implementation Plan: Domain IDs, messages and errors"
status: completed
plan_id: PLAN-F-0001
related_spec: F-0001
created: 2026-08-10
last_updated: 2026-08-10
---

# Implementation Plan: Domain IDs, messages and errors

Related Spec: `docs/specs/F-0001-domain-ids-messages-errors.md`

## Preconditions

- Spec status is `accepted`.
- P1 kickoff 已确认 UUID4、文本/工具消息范围和安全错误边界。
- ADR-0001、ADR-0002 与 ADR-0007 为 `accepted`。

## Vertical slices

### Slice 1: 类型化 ID 与 schema 基线

- Status：completed。
- Domain/contracts：冻结的 UUID4 ID types 和可注入 generator。
- Adapter/interface：P0 store port 与 fake store 改用 `RunId/EventId`。
- Tests：生成、解析、类型隔离、JSON 和非法 UUID 测试。
- Verification command：`uv run pytest tests/unit/test_ids.py tests/unit/test_testing_adapters.py`。
- Rollback point：删除 ID 模块并恢复 P0 字符串契约；无持久数据。

### Slice 2: Provider 无关 Message 与安全 Error

- Status：completed。
- Domain/contracts：Message role/parts、ErrorInfo、BearAgentError。
- Adapter/interface：FakeModelProvider 请求改用 Message。
- Tests：合法 round-trip、非法组合、unknown fields、secret detail keys 和大小限制。
- Verification command：`uv run pytest tests/unit/test_messages.py tests/security/test_domain_errors.py`。
- Rollback point：恢复 P0 string messages；无外部调用。

### Slice 3: 版本化 Event envelope

- Status：completed。
- Domain/contracts：完整通用 envelope、时区与 JSON-only payload validation。
- Adapter/interface：InMemoryEventStore 使用类型化 envelope。
- Tests：sequence、时间、payload、ordering 和 duplicate ID。
- Verification command：`uv run pytest tests/unit/test_events.py tests/unit/test_testing_adapters.py`。
- Rollback point：恢复 P0 Event；无 SQLite migration。

### Slice 4: Schema compatibility 与文档关闭

- Status：completed。
- Domain/contracts：公共 schema registry/snapshot。
- Adapter/interface：domain exports 和 architecture claim 同步。
- Tests：JSON schema snapshot、import boundary、完整回归。
- Verification command：完整 Definition of Done 命令。
- Rollback point：在 F-0002 前整体回退 F-0001；没有持久化兼容负担。

## Cross-cutting checks

- [x] Persistence/recovery：本 Feature 无持久 adapter；回退不涉及 migration。
- [x] Permission/security：覆盖 secret detail key、unknown field 与 Provider object 拒绝测试。
- [x] Timeout/cancel/resource limits：无外部调用；Message/Error/JSON 容器均有结构与大小限制。
- [x] Logs/trace/metrics：Event 提供 correlation/causation/sequence，Error 提供稳定聚合字段。
- [x] Migration/rollback：P0 内部契约一次性替换，无已持久化 schema。
- [x] Documentation impact：Spec、ADR、Plan、索引、Roadmap 和 schema snapshot 已同步。

## Final verification

```text
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
```

结果（2026-08-10）：39 tests passed；Ruff、Pyright 和文档链接检查通过；最终关闭前再次运行。
