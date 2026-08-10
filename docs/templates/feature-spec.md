---
title: "Feature: <name>"
status: draft
spec_id: F-NNNN
milestone: P<n>
owner: <name>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
implemented_in: null
related_adrs: []
---

# Feature: <name>

Filename: `docs/specs/F-NNNN-<slug>.md`

## 1. Background / Problem

当前用户问题和可验证证据是什么？

## 2. Goals

- G-1:

## 3. Non-goals

- NG-1:

## 4. Terms and assumptions

复用架构 glossary；只定义本功能新增术语。列出需要确认的假设。

## 5. User scenarios

### Scenario A

Given / When / Then。

## 6. Functional requirements

- FR-1:
- FR-2:

## 7. Interfaces

CLI、API、Tool schema、Event 或配置如何变化？没有则写 None。

## 8. State and data model

状态转换、Event、projection、migration 和兼容性。

## 9. Failure and recovery semantics

timeout、retry、cancel、crash、partial success、`UNKNOWN` 如何处理？

## 10. Security and privacy

权限、信任边界、secrets、输入校验、资源限制。

## 11. Observability

需要记录的 Event、日志字段、trace、metric 和审计信息。

## 12. Rollout and rollback

本地/服务器启用顺序、feature flag、迁移与回退。

## 13. Acceptance criteria

- AC-1: 可执行且二值判断的标准。
- AC-2:

## 14. Test plan

- Unit:
- Contract:
- Integration:
- Recovery:
- Security:
- Eval/manual:

## 15. Documentation impact

- [ ] Engineering source of truth (`docs/`)
- [ ] Site beginner learning path
- [ ] Site developer documentation
- [ ] Site current status / milestone summary
- [ ] Architecture / ADR
- [ ] Deployment docs
- [ ] Generated reference

Every Feature must update the three `site/` surfaces above. If no dedicated article is needed, identify the existing index or page that will be updated.

## 16. Open questions

- OQ-1:
