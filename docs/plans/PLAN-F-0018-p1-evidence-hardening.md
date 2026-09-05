---
title: "Implementation Plan: F-0018 P1 evidence hardening"
status: completed
plan_id: PLAN-F-0018
related_spec: F-0018
created: 2026-08-28
last_updated: 2026-09-02
---

# PLAN-F-0018：强化 P1 执行契约身份与 crash observability

关联 Spec：`docs/specs/F-0018-p1-evidence-hardening.md`

## 开始前确认

- [x] Spec status is `accepted`.
- [x] 影响实现的开放问题已经解决。
- [x] S2 的 ADR-0016 已接受，迁移/回退边界已经明确。

## 实施步骤

### 第 1 步：建立 contract fingerprint Value Objects 与 canonical hash

- 状态：completed；
- 交付结果：ToolSpec version、Policy/Tool/Run fingerprint、稳定 canonical JSON + SHA-256；
- 代码落点：`domain/tools.py`、新的 domain/runtime fingerprint 模块、`runtime/policy.py`、四个 workspace Tool；
- 接入关系：Registry 提供注册时 ToolSpec；FixedToolPolicy 提供静态 identity；纯 builder 只返回 domain 类型；
- 重点测试：排序稳定、字段变化、版本规则、严格 schema、secret/路径拒绝；
- 验证命令：fingerprint/tool/policy unit 与 contract/security tests；
- 回退方式：在 Event v4 写入前可以删除新类型/字段；不得手工修改 schema snapshot。

### 第 2 步：用 RunCreated v4 持久化并通过 inspect 展示

- 状态：completed；
- 交付结果：production composition 构造 fingerprint；AgentLoop 新 Run 统一写 v4；query/CLI 展示；
- 代码落点：`bootstrap.py`、`application/agent_loop.py`、`domain/run_events.py`、`domain/queries.py`、
  `application/run_queries.py`、CLI renderer/contracts/schema registry；
- 接入关系：bootstrap 注入 domain fingerprint；EventStore 保存 v4 JSON；query 从 Event 读取，不读 adapter；
- 重点测试：v1-v4 reducer/store/context/query compatibility、production composition、human/JSON inspect；
- 验证命令：domain/schema/store/AgentLoop/query/CLI targeted tests；
- 回退方式：保留 v4 parser/query 后停止新 Run 创建；不改旧 Event 或 SQLite migration。

### 第 3 步：固定 failure hint 与 recovery permission 边界

- 状态：completed；
- 交付结果：ErrorInfo/ToolRetrySafety 注释和 schema 语义一致；retryable provider/tool 只执行一次；
- 代码落点：domain errors/tools、recovery/security tests 与相关工程文档；
- 接入关系：现有 Provider/Tool error 继续进入 AgentLoop；没有新 recovery policy；
- 重点测试：provider retryable error、Tool retryable failure、NOT_SAFE workspace write contract；
- 验证命令：AgentLoop/ToolExecutor/recovery/security targeted tests；
- 回退方式：测试与注释可独立回退；不改旧 Event 字段名或值。

### 第 4 步：建立 K1-K6 hard-process crash observability suite

- 状态：completed；
- 交付结果：无 sleep 的 child-process driver，K1-K6 在新 adapter/CLI 进程中复核 committed facts；
- 代码落点：`tests/recovery/` 子进程 driver、fixtures 和 crash suite；production 代码不增加 recovery hook；
- 接入关系：child 使用 SQLite、AgentLoop、workspace.write 和测试 wrapper；parent 通过 query/CLI 读取；
- 重点测试：Event/projection/file/call marker/inspect/events、K4 无伪成功、K5 transaction rollback；
- 验证命令：`uv run pytest tests/recovery/test_crash_observability.py -q`；
- 回退方式：删除测试 harness 不影响 production；不得通过生产 reconcile 让测试通过。

### 第 5 步：同步文档与所有质量门，关闭 Feature

- 状态：completed；
- 交付结果：Roadmap/Architecture/indexes/site/schema/status 与代码一致，Plan/Spec 准确收口；
- 代码落点：Feature 文档列出的五个文档表面和 generated snapshots；
- 接入关系：学习页解释用户可见 inspect；开发者页解释 identity/Event v4/crash boundary；
- 重点测试：governance、docs links、site build、schema idempotence、package/wheel smoke、全量回归；
- 验证命令：本 Plan 最终验证列表；
- 回退方式：Feature 未通过全部门禁时保持 active/accepted，不声明实现完成。

## 跨切片检查

| 风险面 | 结果或 `N/A` + 原因 | 证据 |
|---|---|---|
| Persistence / recovery | v4 只扩展 payload JSON；旧 Event 可读；K1-K6 不恢复 | 474 tests at closure；481 tests after audit |
| Permission / security | fingerprint 严格拒绝配置/Grant 字段，production Event 不含 Provider key | security + composition tests |
| Timeout / cancel / limits | 既有上限不变；retryable Provider/Tool 各只调用一次 | recovery tests |
| Migration / rollback | 无 SQL migration；v4 reader 必须保留 | ADR-0016 |
| Logs / trace / metrics | 不新增 trace；inspect/events 只展示 committed Event | K1-K6 CLI assertions |
| Documentation impact | docs、学习页、开发者页、当前状态和 schema 已同步 | docs/site checks |

## 最终验证

计划运行：

```powershell
$env:UV_CACHE_DIR='D:\BearAgent\.uv-cache'
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --basetemp=.pytest-tmp-f0018 -o cache_dir=.pytest-state-f0018
uv run python scripts/generate_domain_schemas.py
uv run python scripts/generate_cli_schemas.py
uv run python scripts/generate_runtime_configuration_schemas.py
uv run python scripts/check_governance.py
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
uv build
git diff --check
```

2026-08-29 实际结果：

- `uv lock --check`、Ruff、format、Pyright、governance、140 个 Markdown 本地链接和 `git diff --check`
  通过；
- 全量 pytest：474 passed；其中 K1-K6 使用 5 个 hard-exit 子进程和 1 个 SQLite transaction 故障注入；
- domain、CLI、runtime configuration 三组 schema 生成后 contract tests 通过；
- Starlight production build：45 pages，Pagefind 索引完成；
- sdist/wheel 构建成功，隔离安装 wheel 后的 `run/inspect/events` smoke 通过；
- immutable implementation evidence：`commit 26f3203`；Feature `implemented_in`、Roadmap 与索引已同步，
  第 5 步和本 Plan 完成。

## 2026-09-02 完成后全仓审计

- 修复 `validate_event_history` 只列举 schema v2/v3、导致 v4 Tool terminal evidence 绕过原始请求
  一致性检查的问题；现在按解析后的 v2-shaped payload 类型分派，v2/v3/v4 都运行同一规则；
- `ToolRegistry` 构造时只读取每个 Tool 的一次冻结 `ToolSpec`，避免名称索引与真正用于 Policy、Provider
  schema 和 fingerprint 的注册快照分叉；
- 合并 CLI 三个命令中语义重复的异常分支；删除未调用的 OpenAI 私有 helper 和未实现的空
  `adapters/sandbox` 占位包，没有新增 P2/P3 类型或行为；
- 同步 Spec、ADR、Architecture、Roadmap，以及 Reducer、EventStore、Tool、AgentLoop、milestone 和状态
  开发者文档；学习页与 README 为 `N/A`，因为合法 CLI 行为和读者操作路径没有变化；
- 最终结果：481 tests passed；Ruff、format、Pyright、三个 schema 生成器、governance、140 个 Markdown
  链接、45 页 Starlight build、sdist/wheel 和隔离安装后的 `doctor`、`run/inspect/events` smoke 全部通过；
  domain/CLI/runtime configuration schema 与 SQLite migration 均无变化。
