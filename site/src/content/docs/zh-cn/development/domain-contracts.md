---
title: F-0001 开发者实现导读
description: 领域 ID、Message、Error 和 Event envelope 的代码地图与验证方式。
bearStatus: implemented
sourceRefs:
  - F-0001
  - ADR-0007
  - domain schema snapshot
---

初学者导读解释了[为什么先建立领域契约](../architecture/domain-contracts.md)；本页继续说明如何从
代码和测试验证 F-0001。

## 代码地图

| 范围 | 位置 | 责任 |
|---|---|---|
| ID | `src/bearagent/domain/ids.py` | 不透明 UUID4 类型与可注入生成器 |
| Message | `src/bearagent/domain/messages.py` | Provider 无关的 role 和 discriminated parts |
| Error | `src/bearagent/domain/errors.py` | 稳定分类、安全详情和可展示异常 |
| Event | `src/bearagent/domain/events.py` | 不可变、版本化、JSON-only 的通用 envelope |
| Schema | `src/bearagent/domain/schema.py` | 公共 schema registry 与 snapshot 输入 |

这些类型经过 `domain/__init__.py` 暴露给内部 Port。Provider Adapter 必须做显式翻译，不能把
SDK response 类型传入 Runtime。

## 修改契约前要检查什么

- 新字段是否属于稳定领域事实，还是某个 Provider/数据库的实现细节；
- 旧 JSON 的含义是否变化，是否需要新的 schema version；
- unknown field、非法组合和非 JSON 数据是否仍在边界失败；
- Error 是否可能包含 token、authorization、cookie 或原始异常；
- schema snapshot 的变化是否是有意兼容性决策。

## 验证证据

```powershell
uv run pytest tests/unit/test_ids.py tests/unit/test_messages.py
uv run pytest tests/unit/test_events.py tests/security/test_domain_errors.py
uv run pytest tests/contract/test_domain_schemas.py
uv run pyright
```

完整测试仍以仓库 Definition of Done 为准。F-0001 没有实现 Run reducer、SQLite、真实 Provider
或 Tool，这些名称出现在接口规划中不表示当前可用。
