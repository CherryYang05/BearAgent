# Feature Specs

Feature Spec 描述一个可观察行为的目标、非目标、失败语义和验收标准。

`F-NNNN` 是全项目稳定 ID，所属阶段由每份 Spec Front Matter 的 `milestone: P<n>` 显式声明。Feature 调整阶段时只修改 `milestone`，不得重编号。相关架构决定通过 `related_adrs` 引用；ADR 被接受不代表 Feature 已实现。

流程：

```text
draft -> accepted -> implemented -> superseded
```

使用 [Feature Spec 模板](../templates/feature-spec.md)。Feature Spec 文件名统一为 `F-NNNN-<slug>.md`，与 Front Matter 的 `spec_id` 保持一致。

## P0：Engineering Baseline

- [F-0000: P0 Engineering Baseline](F-0000-p0-engineering-baseline.md)

## P1+

### P1：Inspectable Execution

- [F-0001: Domain IDs, messages and errors](F-0001-domain-ids-messages-errors.md)
- [F-0002: Run reducer, Activity lifecycle and budgets](F-0002-run-reducer-activity-lifecycle-budgets.md) — implemented
- [F-0015: Local Starlight documentation site](F-0015-local-starlight-docs-site.md)

其余计划中的 Feature 及 milestone 映射见 [Roadmap 的 Feature Backlog](../project/roadmap.md#12-第一批-feature-backlog)；开始实现前才从模板创建 Spec，并在这里按 `milestone` 分组登记。
