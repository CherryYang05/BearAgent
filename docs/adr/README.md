# 架构决定（ADR）

ADR 只记录影响多个模块、以后难以反转的技术决定。标题直接写出决定，正文用具体冲突解释为什么
必须统一做法。`accepted` 表示决定已经生效，不表示所有相关代码已经实现。

- [ADR-0001：P0–P3 使用 Python 和单进程](ADR-0001-python-single-process-first.md)
- [ADR-0002：Event 是执行事实，恢复只发生在已保存边界](ADR-0002-event-log-safe-boundary-recovery.md)
- [ADR-0003：第一版使用 SQLite 保存执行记录](ADR-0003-sqlite-initial-durable-store.md)
- [ADR-0004：权限由 Runtime 判断，不由模型授予](ADR-0004-policy-outside-model.md)
- [ADR-0005：主 Runtime 进程不执行模型生成的 shell](ADR-0005-no-host-shell-execution.md)
- [ADR-0006：P0 只引入建立工程基线所需的依赖](ADR-0006-p0-tooling-and-dependencies.md)
- [ADR-0007：BearAgent 模块之间只交换 BearAgent 数据类型](ADR-0007-provider-neutral-domain-schemas.md)
- [ADR-0008：公共文档站使用 Starlight](ADR-0008-starlight-public-docs.md)
- [ADR-0009：Run 状态和预算都从 Event 计算](ADR-0009-event-driven-run-state-and-budget-accounting.md)
- [ADR-0010：首个生产模型 adapter 使用 OpenAI Responses](ADR-0010-openai-responses-first-model-adapter.md)
- [ADR-0011：workspace Tool 只接受可移植相对路径，并且不跟随链接](ADR-0011-workspace-relative-paths-no-links.md)
  — accepted
- [ADR-0012：P1 输出先原子替换，再由用户管理 Artifact 生命周期](ADR-0012-atomic-user-managed-output-artifacts.md)
  — accepted
- [ADR-0013：P1 Agent Loop 串行执行，并在外部调用前后保存 Activity 事实](ADR-0013-serial-agent-loop-event-boundaries.md)
  — accepted
- [ADR-0014：CLI 只调用 application command，生产依赖只在 bootstrap 组装](ADR-0014-cli-calls-application-production-wiring-stays-in-bootstrap.md)
  — accepted
- [ADR-0015：用户配置显式选择模型协议 adapter](ADR-0015-explicit-model-protocol-adapters.md)
  — accepted
- [ADR-0016：Run 创建时保存可信契约身份，进程中断后只报告已提交事实](ADR-0016-run-contract-fingerprint-committed-crash-facts.md)
  — accepted
- [ADR-0017：系统只用 Event 确认执行结果，诊断日志只帮助排错](ADR-0017-event-ledger-with-best-effort-ops-diagnostics.md)
  — accepted

- [ADR-0018：文件工具在打开内容之前排除 Runtime 的配置和记录](ADR-0018-runtime-files-outside-workspace-tools.md)
  — accepted
- [ADR-0019：main 推送成功后使用受限身份发布静态文档](ADR-0019-main-push-deploys-docs-with-restricted-key.md)
  — accepted

新决定使用 [ADR 模板](../templates/adr.md)。被新决定替代的 ADR 不删除，改为 `superseded` 并链接
到替代它的文档。
