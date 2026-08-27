# Implementation Plans

Plan 说明一个已接受 Feature 准备按什么顺序落到代码。S2 必须有 Plan；S1 只有在需要多个独立验证
切片、跨多个提交/PR，或无法作为一个连贯变更安全评审时才创建。每一步完成后都应能单独验证，
仓库同时最多只有一个 `active` 主 Plan。

命名为 `PLAN-F-NNNN-<slug>.md`，Front Matter 至少包含：

```yaml
status: draft | active | completed | superseded
plan_id: PLAN-F-NNNN
related_spec: F-NNNN
```

Plan 不重复 Spec 的需求，也不代替 ADR。开始前确认 Spec 已 `accepted`，影响实现的开放问题已经
解决；完成后根据代码和测试把 Plan 改为 `completed`、Spec 改为 `implemented`。完成的 Plan 保留为
历史证据，但日常开发只读取当前 Feature 的 Spec、相关 ADR 和 active Plan。

新 Plan 使用 [Implementation Plan 模板](../templates/implementation-plan.md)。

## 当前计划

- 无。

## 已完成计划

- [PLAN-F-0015：建立并重写 Starlight 文档站](PLAN-F-0015-local-starlight-docs-site.md)
- [PLAN-F-0001：内部 ID、Message、Error 和 Event](PLAN-F-0001-domain-ids-messages-errors.md)
- [PLAN-F-0002：Run/Activity 状态和预算](PLAN-F-0002-run-reducer-activity-lifecycle-budgets.md)
- [PLAN-F-0003：EventStore、SQLite 和 projection](PLAN-F-0003-event-store-sqlite-projections.md)
- [PLAN-F-0004：ModelProvider 和首个生产 adapter](PLAN-F-0004-model-provider-first-adapter.md)
- [PLAN-F-0006：统一 Tool Registry、Executor 和 P1 固定 Policy](PLAN-F-0006-tool-registry-executor-policy.md)
- [PLAN-F-0007：实现有界的 workspace 只读 Tool](PLAN-F-0007-workspace-read-tools.md)
- [PLAN-F-0008：实现 outputs 原子写入和 Artifact 元数据](PLAN-F-0008-atomic-output-artifacts.md)

- [PLAN-F-0016：实现有界 Context 和串行 Agent Loop](PLAN-F-0016-bounded-context-agent-loop.md)
- [PLAN-F-0005：接通生产 Run、inspect 和 events CLI](PLAN-F-0005-run-inspect-events-cli.md)
- [PLAN-F-0017：配置模型服务协议并完成 P1 真实模型 gate](PLAN-F-0017-configurable-model-providers-live-gate.md)
