---
title: F-0001：修改内部数据类型
description: ID、Message、Error 和 Event 的代码入口、修改顺序与验证方法。
bearStatus: implemented
sourceRefs:
  - F-0001
  - ADR-0007
  - domain schema snapshot
---

F-0001 规定 Runtime 内部交换哪些数据。修改这里会同时影响后续模型、存储、工具和 CLI，因此先
判断新字段是不是 BearAgent 长期需要的事实，而不是某个 SDK 或数据库恰好提供的字段。

## 代码入口

| 文件 | 负责什么 |
|---|---|
| `src/bearagent/domain/ids.py` | 各种 UUID4 ID 和可替换的 ID 生成器 |
| `src/bearagent/domain/messages.py` | 四种消息角色，以及文本、工具请求和工具结果 |
| `src/bearagent/domain/errors.py` | 稳定错误分类和可以安全展示的详情 |
| `src/bearagent/domain/events.py` | 所有 Event 共用的 ID、顺序、版本和时间字段 |
| `src/bearagent/domain/schema.py` | 参与 JSON schema 快照比较的类型登记 |

`domain/__init__.py` 对内部模块暴露这些类型。模型 adapter 必须把 SDK 响应显式转换成 Message；
Runtime 不接受 SDK response 类型。

## 修改时按这个顺序判断

1. 新字段是否描述 BearAgent 的事实，还是只属于一个 Provider？
2. 已保存 JSON 的含义会不会改变？如果会，是否需要新的 schema version？
3. 非法组合、未知字段和非 JSON 值是否仍会在入口被拒绝？
4. 错误详情会不会带入 token、cookie、authorization 或原始异常？
5. JSON schema 快照为什么变化，旧读取方是否还能理解？

## 验证

```powershell
uv run pytest tests/unit/test_ids.py tests/unit/test_messages.py
uv run pytest tests/unit/test_events.py tests/security/test_domain_errors.py
uv run pytest tests/contract/test_domain_schemas.py
uv run pyright
```

这些测试覆盖 F-0001 数据结构和边界。SQLite、三个模型协议 adapter 与完整 AgentLoop 已分别由后续
Feature 接通并有独立契约/集成测试；修改领域类型时仍要运行这些下游测试。
