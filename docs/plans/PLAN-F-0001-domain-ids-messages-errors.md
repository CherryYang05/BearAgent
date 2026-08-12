---
title: "Implementation Plan: Domain IDs, messages and errors"
status: completed
plan_id: PLAN-F-0001
related_spec: F-0001
created: 2026-08-10
last_updated: 2026-08-13
---

# PLAN-F-0001：内部 ID、Message、Error 和 Event

关联 Spec：`docs/specs/F-0001-domain-ids-messages-errors.md`

## 开始前确认

Spec 与 ADR-0001、ADR-0002、ADR-0007 已接受；UUID4、文本/工具消息范围和安全 Error 边界已经确认。

## 实施步骤

### 第 1 步：用不同类型表示不同 ID

- 状态：completed；
- 交付结果：冻结的 UUID4 ID 类型和可替换生成器；
- 代码落点：`domain/ids.py`，P0 store port 和 Fake store 改用 `RunId/EventId`；
- 接入关系：Application 创建 ID，其他模块只传递对应具体类型；
- 重点测试：生成、解析、类型隔离、JSON 和非法 UUID；
- 验证：`uv run pytest tests/unit/test_ids.py tests/unit/test_testing_adapters.py`；
- 回退：恢复 P0 字符串 ID，无持久数据迁移。

### 第 2 步：统一 Message 和可以安全传播的 Error

- 状态：completed；
- 交付结果：Message 角色/内容、ErrorInfo 和 BearAgentError；
- 代码落点：`domain/messages.py`、`domain/errors.py`，Fake model 请求改用 Message；
- 接入关系：Provider adapter 将来把 SDK 响应翻译成 Message，Application 把外部异常转成安全 Error；
- 重点测试：JSON 往返、非法角色组合、未知字段、敏感详情键和大小限制；
- 验证：`uv run pytest tests/unit/test_messages.py tests/security/test_domain_errors.py`；
- 回退：恢复 P0 字符串消息，无外部调用和持久数据。

### 第 3 步：补全所有 Event 共用的字段

- 状态：completed；
- 交付结果：版本、时间、关联 ID 和 JSON-only payload；
- 代码落点：`domain/events.py`，内存 store 改用完整 Event；
- 接入关系：后续具体 Event payload 复用该外壳，store 按 Run 和 sequence 保存；
- 重点测试：sequence、时区、payload、排序和重复 ID；
- 验证：`uv run pytest tests/unit/test_events.py tests/unit/test_testing_adapters.py`；
- 回退：恢复 P0 Event，无 SQLite migration。

### 第 4 步：建立 schema 兼容性基线并关闭 Feature

- 状态：completed；
- 交付结果：公共 schema registry、快照、exports 和对应文档；
- 代码落点：`domain/schema.py`、schema snapshot、Architecture/ADR/Spec/Site；
- 接入关系：后续公共类型加入 registry，修改时通过快照审查 JSON 变化；
- 重点测试：schema snapshot、import boundary 和完整回归；
- 验证：最终验证命令；
- 回退：在 F-0002 前整体回退 F-0001，无持久兼容负担。

## 每一步都检查过

- [x] 无持久 adapter，回退不涉及 migration；
- [x] 敏感 Error 键、未知字段和 Provider 对象被拒绝；
- [x] 无外部调用，容器和文本有结构与大小限制；
- [x] Event 提供 correlation、causation、sequence，Error 提供稳定聚合字段；
- [x] Spec、ADR、Plan、Architecture、Roadmap、Site 和快照已同步。

## 最终验证

```text
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
```

2026-08-10：39 tests passed，Ruff、Pyright 和文档链接检查通过。
