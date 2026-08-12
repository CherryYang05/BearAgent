# Implementation Plans

Implementation Plan 记录一个已接受 Feature 的实现步骤和当前进度，不重复 Feature Spec 的需求，也不代替 ADR。

命名使用 `PLAN-F-NNNN-<slug>.md`，并在 Front Matter 中声明：

```yaml
status: draft | active | completed | superseded
plan_id: PLAN-F-NNNN
related_spec: F-NNNN
```

规则：

- Feature Spec 达到 `accepted` 且影响实现的开放问题已解决后，Plan 才能从 `draft` 进入 `active`。
- 仓库同时最多只有一个 `active` 主 Plan；小型 S0 修复不需要 Plan。
- 每个步骤的完成状态必须与代码和测试证据一致，不能只依据聊天记录勾选。
- Feature 验收完成后，Plan 标记 `completed`，Feature Spec 标记 `implemented`。
- Feature 所属 milestone 从关联 Spec 推导，Plan 不重复维护。

使用 [Implementation Plan 模板](../templates/implementation-plan.md)。

当前 active Plan：

- 无。下一主 Feature 尚未由项目所有者确认。

已完成：

- [PLAN-F-0004: ModelProvider internal interface and first production adapter](PLAN-F-0004-model-provider-first-adapter.md)
- [PLAN-F-0003: EventStore contract, SQLite adapter and projections](PLAN-F-0003-event-store-sqlite-projections.md)
- [PLAN-F-0002: Run reducer, Activity lifecycle and budgets](PLAN-F-0002-run-reducer-activity-lifecycle-budgets.md)
- [PLAN-F-0015: Local Starlight documentation site](PLAN-F-0015-local-starlight-docs-site.md)
- [PLAN-F-0001: Domain IDs, messages and errors](PLAN-F-0001-domain-ids-messages-errors.md)
