# Implementation Plans

Plan 说明一个已接受 Feature 准备按什么顺序落到代码。每一步完成后都应能单独验证，仓库同时最多
只有一个 `active` 主 Plan。

命名为 `PLAN-F-NNNN-<slug>.md`，Front Matter 至少包含：

```yaml
status: draft | active | completed | superseded
plan_id: PLAN-F-NNNN
related_spec: F-NNNN
```

Plan 不重复 Spec 的需求，也不代替 ADR。开始前确认 Spec 已 `accepted`，影响实现的开放问题已经
解决；完成后根据代码和测试把 Plan 改为 `completed`、Spec 改为 `implemented`。

新 Plan 使用 [Implementation Plan 模板](../templates/implementation-plan.md)。

## 当前计划

没有 active Plan。下一个 P1 Runtime Feature 需要项目所有者确认后再开始。

## 已完成计划

- [PLAN-F-0001：内部 ID、Message、Error 和 Event](PLAN-F-0001-domain-ids-messages-errors.md)
- [PLAN-F-0002：Run/Activity 状态和预算](PLAN-F-0002-run-reducer-activity-lifecycle-budgets.md)
- [PLAN-F-0003：EventStore、SQLite 和 projection](PLAN-F-0003-event-store-sqlite-projections.md)
- [PLAN-F-0004：ModelProvider 和首个生产 adapter](PLAN-F-0004-model-provider-first-adapter.md)
- [PLAN-F-0015：本地 Starlight 文档站](PLAN-F-0015-local-starlight-docs-site.md)
