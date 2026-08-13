---
title: F-0001 开发者实现导读
description: 内部 ID、Message、Error 和 Event 通用外壳的代码地图与验证方式。
bearStatus: implemented
sourceRefs:
  - F-0001
  - ADR-0007
  - domain schema snapshot
---

初学者导读解释了[为什么先统一内部数据格式](../architecture/domain-contracts.md)；本页继续说明如何从
代码和测试验证 F-0001。

## 代码地图

| 范围 | 位置 | 责任 |
|---|---|---|
| ID | `src/bearagent/domain/ids.py` | 不透明 UUID4 类型与可注入生成器 |
| Message | `src/bearagent/domain/messages.py` | 不依赖特定模型服务商的消息角色和带类型标识的内容块 |
| Error | `src/bearagent/domain/errors.py` | 稳定分类、安全详情和可展示异常 |
| Event | `src/bearagent/domain/events.py` | 不可变、带版本、只含 JSON 数据的通用外壳 |
| 数据格式 | `src/bearagent/domain/schema.py` | 公共数据格式清单与 JSON Schema 快照输入 |

这些类型经过 `domain/__init__.py` 暴露给 Port（内部接口）。模型服务适配器必须显式翻译，不能把
SDK 响应类型传入运行时。

## 修改内部数据格式或规则前要检查什么

- 新字段是否属于稳定的内部事实，还是某个模型服务商或数据库的实现细节；
- 旧 JSON 的含义是否变化，是否需要新的数据格式版本；
- unknown field、非法组合和非 JSON 数据是否仍在边界失败；
- Error 是否可能包含 token、authorization、cookie 或原始异常；
- JSON Schema 快照的变化是否是有意的兼容性决策。

## 验证证据

```powershell
uv run pytest tests/unit/test_ids.py tests/unit/test_messages.py
uv run pytest tests/unit/test_events.py tests/security/test_domain_errors.py
uv run pytest tests/contract/test_domain_schemas.py
uv run pyright
```

完整测试仍以仓库的完成标准为准。F-0001 本身没有实现 Run reducer、SQLite、真实模型服务
或 Tool；其中 SQLite 和真实模型服务由后续 Feature 实现，Tool 目前仍不可用。
