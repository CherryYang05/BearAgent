# Architecture Decision Records

ADR 记录已经接受、跨模块且代价较高的技术决定。新决定从模板复制，编号递增；文件名统一为 `ADR-NNNN-<slug>.md`，与文档中的 ADR ID 保持一致。被替代 ADR 保留并标记 `superseded`。

- [ADR-0001: Python 与单进程优先](ADR-0001-python-single-process-first.md)
- [ADR-0002: Event log 与安全边界恢复](ADR-0002-event-log-safe-boundary-recovery.md)
- [ADR-0003: SQLite 作为初始 durable store](ADR-0003-sqlite-initial-durable-store.md)
- [ADR-0004: 权限策略位于模型之外](ADR-0004-policy-outside-model.md)
- [ADR-0005: Host runtime 不执行模型生成 shell](ADR-0005-no-host-shell-execution.md)
- [ADR-0006: P0 工具链与依赖基线](ADR-0006-p0-tooling-and-dependencies.md)
- [ADR-0007: Provider 无关的领域 schema](ADR-0007-provider-neutral-domain-schemas.md)
- [ADR-0008: 公共文档站使用 Starlight](ADR-0008-starlight-public-docs.md)
- [ADR-0009: Event 驱动的 Run 状态与预算记账](ADR-0009-event-driven-run-state-and-budget-accounting.md)
