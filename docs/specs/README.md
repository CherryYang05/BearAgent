# Feature Specs

Feature Spec 说明一个功能为什么要做、必须出现哪些行为、失败时用户会看到什么，以及怎样判断完成。
它不是架构介绍，也不规定实现顺序。

Feature ID `F-NNNN` 在全项目稳定，所属阶段写在 Front Matter 的 `milestone` 中。移动阶段时只修改
`milestone`，不改 ID。相关 ADR 说明技术决定；ADR 被接受不表示 Feature 已实现。

状态顺序：

```text
draft -> accepted -> implemented -> superseded
```

新 Spec 使用 [Feature Spec 模板](../templates/feature-spec.md)，文件名为 `F-NNNN-<slug>.md`。

S1 使用精简范围：问题、目标/非目标、可观察行为、必要失败边界、验收标准和文档影响。S2 才完整
展开状态、持久化、恢复、安全、迁移和回退，并配套 ADR 与 Plan。Spec Front Matter 是 Feature 状态
的唯一登记；本索引由 `scripts/check_governance.py` 校验，不建立第二份 registry。

## P0：工程基础

- [F-0000：建立可安装、可测试的工程基础](F-0000-p0-engineering-baseline.md) — implemented

## P1：可检查执行

- [F-0001：统一内部 ID、Message、Error 和 Event 外壳](F-0001-domain-ids-messages-errors.md) — implemented
- [F-0002：从 Event 计算 Run/Activity 状态和预算](F-0002-run-reducer-activity-lifecycle-budgets.md) — implemented
- [F-0003：使用 SQLite 原子保存 Event 和 projection](F-0003-event-store-sqlite-projections.md) — implemented
- [F-0004：建立模型内部接口和首个生产 adapter](F-0004-model-provider-first-adapter.md) — implemented
- [F-0005：从命令行运行文件任务，并查看同一批已保存事实](F-0005-run-inspect-events-cli.md) — implemented
- [F-0006：所有 Tool 请求经过同一个执行和权限入口](F-0006-tool-registry-executor-policy.md) — implemented
- [F-0007：把 workspace 中的目录和文本安全地交给 Agent 阅读](F-0007-workspace-read-tools.md) — implemented
- [F-0008：只把完整结果写进 outputs，并返回可核对的 Artifact](F-0008-atomic-output-artifacts.md) — implemented
- [F-0016：把模型、Tool 和 Event 接成一条有界的文件任务执行链](F-0016-bounded-context-agent-loop.md) — implemented
- [F-0015：建立可以连续阅读的中文文档站](F-0015-local-starlight-docs-site.md) — implemented
  （本地开发、构建、预览、书籍化路线和 CLI 手册已完成；在线托管不在 Feature 范围内）
- [F-0017：配置自己的模型服务，并用真实模型完成可检查文件任务](F-0017-configurable-model-providers-live-gate.md) — implemented
- [F-0018：记录 Run 使用的可信执行契约，并展示进程中断前最后确认的事实](F-0018-p1-evidence-hardening.md) — implemented
- [F-0019：安全输出结构化运行诊断，而不复制 Event 内容](F-0019-safe-structured-diagnostics.md) — implemented

- [F-0020：保护本机运行资料并简化首次使用](F-0020-safe-local-startup.md) — accepted

其余计划 Feature 见[路线图 Backlog](../project/roadmap.md#11-feature-backlog)。未创建 Spec 的名称只是
计划范围，不能授权实现。
