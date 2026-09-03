---
title: "Implementation Plan: Safe structured operational diagnostics"
status: active
plan_id: PLAN-F-0031
related_spec: F-0031
created: 2026-09-02
last_updated: 2026-09-02
---

# PLAN-F-0031：安全结构化运行诊断

关联 Spec：`docs/specs/F-0031-safe-structured-diagnostics.md`

## 开始前确认

- [x] Spec status is `accepted`.
- [x] 影响实现的开放问题已经解决。
- [x] S2 的 ADR 已接受，迁移/回退边界已经明确。

## 实施步骤

### 第 1 步：建立字段封闭的 record、sink port 与标准库 adapter

- 状态：completed；
- 交付结果：冻结 DiagnosticRecord、sink protocol、Null/JSON Lines adapter 和 fail-open emitter；
- 代码落点：`domain/diagnostics.py`、`ports/diagnostics.py`、`adapters/diagnostics.py`；
- 接入关系：外层调用只传 BearAgent record，adapter 只向 stderr 输出固定 JSON；
- 重点测试：字段校验、byte limit、确定性 JSON、sink failure 隔离；
- 验证命令：`uv run pytest tests/unit/test_diagnostics.py -q`；
- 回退方式：删除新增模块，不影响 Event 与数据库。

### 第 2 步：在 EventStore 提交后输出 ledger 元数据

- 状态：completed；
- 交付结果：decorator 输出 committed/append failed/query failed record，并计算有界耗时；
- 代码落点：diagnostics adapter 与 production bootstrap；
- 接入关系：AgentLoop/RunQueryService 继续只依赖同一个 EventStore port；
- 重点测试：post-commit 顺序、payload 不复制、Activity duration、append/query/sink failure；
- 验证命令：`uv run pytest tests/unit/test_diagnostics.py tests/unit/test_bootstrap.py -q`；
- 回退方式：bootstrap 直接恢复使用 SqliteEventStore。

### 第 3 步：接通 CLI/Bootstrap 安全失败并完成安全回归

- 状态：completed；
- 交付结果：stdout contract 不变，stderr 输出有限 operation error；
- 代码落点：bootstrap、CLI error boundary、security/integration tests；
- 接入关系：CLI 仍只调用 application/bootstrap，不读取日志作业务判断；
- 重点测试：secret/raw exception/path/objective 不泄漏，Null/failing sink 不改变结果；
- 验证命令：`uv run pytest tests/integration/test_run_cli.py tests/security/test_diagnostics.py -q`；
- 回退方式：移除最外层诊断调用，保留原安全 Error renderer。

### 第 4 步：同步工程与读者文档并完成全量验证

- 状态：completed；
- 交付结果：架构、路线图、CLI/开发者页准确区分 Event、Log、Trace；
- 代码落点：Spec/ADR/Plan、architecture/roadmap、site；
- 接入关系：文档只解释当前实现，不把 P5 OTel 写成现状；
- 重点测试：governance、links、Starlight build、全量质量门；
- 验证命令：见最终验证；
- 回退方式：随实现回退对应事实说明，不删除历史 Spec/ADR。

## 跨切片检查

| 风险面 | 结果或 `N/A` + 原因 | 证据 |
|---|---|---|
| Persistence / recovery | 不改变持久状态；日志永不作为恢复输入 | post-commit/failing sink tests |
| Permission / security | 固定字段排除正文、路径、secret、原始异常 | security scan |
| Timeout / cancel / limits | stderr line 有 byte 上限；取消不被 sink 捕获 | unit tests |
| Migration / rollback | 无 Event/SQLite/CLI JSON migration；可移除 wiring | schema/migration diff |
| Logs / trace / metrics | 本 Feature 只做本地 logs；OTel/metrics/完整 trace 留在 P5 | ADR-0017 |
| Documentation impact | 按 Spec 第 9 节逐面同步 | docs/site checks |

## 最终验证

完成前运行并记录：

```text
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
uv run python scripts/check_governance.py
uv run python scripts/check_docs.py
npm run build --prefix=site
git diff --check
```

在取得独立 commit/PR 证据前，Feature 保持 `accepted`、Plan 保持 `active`；本 Plan 要准确记录已经完成
的技术切片，但不把未授权的 commit/push 当作完成证据。

## 2026-09-02 工作树验证结果

- `uv run ruff check .`、`uv run ruff format --check .` 和 `uv run pyright` 通过；
- `uv run pytest -q` 通过 490 个测试；
- 三个 schema generator 运行后 snapshot 无 diff；
- governance 检查通过 14 个 Spec、13 个 Plan、17 个 ADR；144 个 Markdown 本地链接通过；
- Starlight 构建 46 页并生成搜索索引；sdist/wheel 构建成功；
- `git diff --check` 通过；没有 Event/CLI/runtime configuration schema 或 SQLite migration 变化；
- 当前仍缺独立 commit/PR immutable evidence，因此 Front Matter 按治理规则保持 `accepted` / `active`。
