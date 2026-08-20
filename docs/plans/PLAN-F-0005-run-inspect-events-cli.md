---
title: "Implementation Plan: Production Run, inspect, and Event CLI"
status: completed
plan_id: PLAN-F-0005
related_spec: F-0005
created: 2026-08-20
last_updated: 2026-08-20
---

# PLAN-F-0005：接通生产 Run、inspect 和 events CLI

关联 Spec：`docs/specs/F-0005-run-inspect-events-cli.md`

## 开始前确认

- [x] F-0005 Spec 已由项目所有者接受，并把 status 从 `draft` 改为 `accepted`；
- [x] ADR-0014 已由项目所有者接受，并把 status 从 `proposed` 改为 `accepted`；
- [x] Spec 第 16 节四项决定均已确认，没有影响实现的开放问题；
- [x] F-0016 已合入 `main`，当前分支从 `main@2b0e90a` 创建；
- [x] 仓库当前没有其他 `active` 主 Plan；
- [x] 以上条件满足，本 Plan 于 2026-08-20 从 `draft` 改为 `active`。

## 实施步骤

### 第 1 步：冻结 Run query 与 CLI JSON 结果契约

Status：completed（2026-08-20）。

- 交付结果：新增严格、冻结、Provider-neutral 的 `RunInspection`、`EventPage`、version 1 CLI result/error
  envelope；定义 UUID、时间、Enum、Event payload、Artifact 和 pagination 的 JSON shape；
- 代码落点：`src/bearagent/domain/` 放可复用 query 结果，`src/bearagent/interfaces/cli/contracts.py` 放
  CLI envelope；分别维护公共 Schema/快照和对应 unit/contract tests；
- 接入关系：EventStore 继续只返回 `RunState/Event`；application 组合 query result；CLI 只渲染；
- 重点测试：[AC-3][AC-4][AC-6] 未知字段、冻结、JSON round-trip、稳定 schema、游标、Artifact 去重/顺序；
- 验证命令：`uv run pytest tests/unit/test_run_queries.py tests/contract/test_cli_schemas.py tests/contract/test_domain_schemas.py`；
- 回退方式：删除尚未接入 CLI 的 query/output 类型并恢复 Schema 快照，不修改 Event 或数据库。

### 第 2 步：实现只依赖 EventStore 的 application query service

Status：completed（2026-08-20）。

- 交付结果：`inspect` 从 projection 加有界 Event 分页构造完整结果；`events` 返回有界页、下一游标和
  `has_more`；缺失 Run、超量、解析/corruption 均返回安全 application error；
- 代码落点：`src/bearagent/application/run_queries.py`、application exports 和 unit tests；
- 接入关系：service 只依赖 EventStore port 和领域解析函数；不导入 SQLite、Typer、Provider 或 workspace；
- 重点测试：[AC-3][AC-4][AC-5] 非终态、terminal Error、Artifact、边界页、空页、超上限、Store failure；
- 验证命令：`uv run pytest tests/unit/test_run_queries.py tests/contract/test_event_store_contract.py`；
- 回退方式：移除 query service；已有 Store port、Event 和 projection 保持不变。

### 第 3 步：建立有界 Run profile 和唯一 production composition root

Status：completed（2026-08-20）。

- 交付结果：严格读取 version 1 JSON profile，先完成大小/UTF-8/字段/领域校验，再组装 SQLite、OpenAI、
  workspace Tools、Registry、FixedToolPolicy、ToolExecutor、AgentLoop 和 query service；支持可信层预生成
  RunId 供 CLI 提前显示；OpenAI SDK client 延迟到首个真实模型 Activity，零预算和缺凭据因此都保留为
  可查询的安全 terminal Run；
- 代码落点：`src/bearagent/bootstrap.py`、必要的 application facade/AgentLoop 兼容参数、profile 示例或
  generated reference，以及 unit/integration/security tests；
- 接入关系：bootstrap 可以导入具体 adapter；application/runtime/domain 继续只依赖 ports/BearAgent 类型；
- 重点测试：[AC-1][AC-7][AC-8] profile 未知/敏感字段、超限/非法 UTF-8、缺失 key、路径、Policy allowlist、
  预生成 ID、初始化顺序、零外部调用；
- 验证命令：`uv run pytest tests/unit/test_bootstrap.py tests/integration/test_run_cli.py tests/security/test_cli_boundaries.py tests/architecture/test_import_boundaries.py`；
- 回退方式：移除 composition/profile；可选 RunId 参数保持兼容或一并回退，不触碰数据库/Artifact。

### 第 4 步：接通 Typer run/inspect/events 和 human/JSON renderer

Status：completed（2026-08-20）。

- 交付结果：在现有 `doctor` 旁增加 run command group；无子命令执行 objective，inspect/events 调用 query
  service；human 输出有限清楚，JSON stdout 单对象；退出码稳定；
- 代码落点：`src/bearagent/interfaces/cli/`、`tests/unit/test_cli.py` 和新的 CLI integration tests；
- 接入关系：handler 只调用 application/bootstrap 暴露的窄接口；renderer 不查询 Store、不调用 adapter；
- 重点测试：[AC-1][AC-2][AC-3][AC-4][AC-6][AC-10] help/解析歧义、human/JSON、stderr、not found、
  failed/non-terminal Run、module/console entrypoint；
- 验证命令：`uv run pytest tests/unit/test_cli.py tests/integration/test_run_cli.py tests/integration/test_module_entrypoint.py`；
- 回退方式：移除新命令与 renderer，保留 `doctor/version`；application/query 可独立保留或随后回退。

### 第 5 步：验证中断、安全边界和安装包

Status：completed（2026-08-20）。

- 交付结果：故障注入覆盖 Run 创建、Activity、terminal append、Ctrl+C、外部写后 append 失败；查询重开
  SQLite 后只显示已提交事实；secret/路径/SQL/SDK 异常不泄漏；wheel 中入口可运行；
- 代码落点：`tests/recovery/`、`tests/security/`、`tests/integration/`、architecture/package verification；
- 接入关系：测试从 CLI/application 入口进入，外部文件动作仍通过 ToolExecutor，查询只通过 EventStore；
- 重点测试：[AC-2][AC-5][AC-7][AC-8][AC-9][AC-10] append failure、active Run、损坏/未来 DB、broken pipe、
  Prompt/profile 提权、console script/wheel；
- 验证命令：`uv run pytest tests/recovery tests/security tests/integration tests/architecture`；
- 回退方式：移除测试 seam 与 F-0005 实现；不删除已产生数据库或 `outputs/**`。

### 第 6 步：运行固定任务、同步四个文档表面并交付 P1 收尾检查点

Status：completed（2026-08-20）。

- 交付结果：Fake Provider 5/5 持续通过；production composition 测试通过注入 Fake Provider 完成，不
  读取真实凭据或发起真实模型请求；完成独立反向审查和完整验证；
- 代码落点：`evals/p1/` 的复用 runner/结果说明、相关 `docs/`、README、
  `site/src/content/docs/zh-cn/learn/`、`development/`、`project/status.md` 和索引；
- 接入关系：离线验证复用 F-0016 task 定义与 F-0005 production composition，不建立第二套 Prompt/Tool；
- 重点测试：[AC-11][AC-12] exact task/profile/model version、Tool 路径、Artifact hash、文档链接、站点、
  Schema、build、wheel 和 Reality Check 清单；
- 验证命令：运行本 Plan 的最终验证；不读取真实凭据、不运行真实模型；
- 回退方式：F-0005 gate 未通过时保持 Feature/P1 未关闭；通过后只关闭 F-0005，P1 保持进行中，等待
  真实模型 API/演练决定和完整 Reality Check。

## 耦合评估

- 新增/修改公共接口：Provider-neutral query/output 模型、application query service、AgentLoop 可选可信
  RunId、CLI command/JSON schema 和 Run profile schema；
- 依赖模块：interfaces 依赖 application/bootstrap；bootstrap 组装 adapters + application；application 只依赖
  domain/runtime/ports；
- 新依赖：无；继续使用 Typer、Pydantic、OpenAI SDK、SQLite stdlib 和现有 uv 工具链；
- 依赖方向：不允许 domain/runtime/application 导入 Typer、OpenAI SDK、SQLite adapter 或 workspace adapter；
- 循环风险：profile loader/renderer 不进入 application；bootstrap 不被 core 导入；query service 不回调 CLI；
- 扇出控制：CLI 参数、human renderer、JSON renderer、profile loader、production composition 和 query service
  分开；`main.py` 不变成同时负责 SQL/Provider/Tool/输出的上帝文件。

## 关键注释原则

- 在 production composition 说明为什么 key/path 不能进入 AgentConfig/Event；
- 在 inspect 的总量上限处说明为什么宁可明确失败，也不能返回假完整 Artifact；
- 在预生成 RunId 处说明 ID 是可信 composition 输入，不是模型/profile 权限；
- 在 Event JSON renderer 说明完整 payload 是显式导出，不是默认日志；
- 不给直接委托、字段映射或显而易见的 Typer 装饰器增加冗余注释。

## 每一步都要检查

- [x] Event/Run projection 语义未复制或分叉，SQLite schema/migration 未改变；
- [x] inspect/events 只读取已提交事实，非终态 Run 不显示成功；
- [x] 所有 workspace 动作继续经过 Registry、prepare、FixedToolPolicy 和 ToolExecutor；
- [x] profile、CLI、Event query 和 renderer 均有大小/数量/timeout 边界；
- [x] API key、authorization、base URL、本机绝对根、SQL 和原始异常不进入 Event/输出；
- [x] Ctrl+C/强制退出不自动 retry/resume，不伪造 terminal 或 `UNKNOWN`；
- [x] human/JSON 共享 application result，JSON stdout 保持单对象；
- [x] domain/runtime/application 没有外层 adapter/SDK/CLI 类型泄漏；
- [x] AC 编号与 Plan 步骤、测试和文档回链；
- [x] 工程文档、初学者路径、开发者文档、当前状态和 P1 milestone 同步。

## 最终验证

```powershell
$env:UV_CACHE_DIR='D:\BearAgent\.uv-cache'
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv run python scripts/generate_domain_schemas.py
uv run python scripts/generate_cli_schemas.py
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
uv build
uv run --isolated --no-project --with .\dist\bearagent-0.1.0-py3-none-any.whl bearagent doctor --json
uv run --directory .\dist --isolated --no-project --with .\bearagent-0.1.0-py3-none-any.whl python ..\scripts\smoke_wheel_cli.py
git diff --check
```

还要从构建出的 wheel 在隔离目录运行 `bearagent doctor`、Fake CLI Run、inspect/events JSON，并确认
console script 与 `python -m bearagent` 一致。本 Feature 的验证不得读取真实凭据或调用真实模型；
F-0005 完成后再向项目所有者提交 P1 真实模型 API/演练与完整 Reality Check 的单独决定。

以上命令没有实际通过前，不得把 Plan 标记为 `completed` 或把 Spec 标记为 `implemented`。F-0005
完成也不得自动把 Roadmap/P1 状态写成已完成。

## 完成证据

2026-08-20 完成离线验收：uv lock、Ruff format/check、Pyright 和 348 项 pytest 全部通过；公共
domain/CLI Schema 重新生成后 hash 不变；89 份 Markdown 的本地链接通过；Starlight 成功构建 34 个
页面；sdist/wheel 构建成功。隔离安装后的 console script、`python -m bearagent`、Fake Provider
`run/inspect/events` smoke test 均通过。pytest 使用同一组仓库本地临时/cache 目录完成，验收后清理，
不保留按步骤递增的测试目录。

验收没有读取真实 Provider 凭据或调用真实模型。F-0005 在此关闭；Roadmap/P1 保持进行中，等待项目
所有者决定真实模型 API/4-of-5 gate，并执行完整 P1 Reality Check。

同日收尾复查补充了 Provider 初始化边界：SDK client 不再在 bootstrap 阶段抢先读取凭据。新增回归
测试分别证明零预算 Run 在任何 Provider client 创建前以 `budget_exhausted` 持久终止，以及非零预算但
缺少凭据时以安全的 `provider_authentication` 持久终止；Fake Provider 仍只通过测试注入，不进入生产
CLI 选项。最终测试数量和完整验证证据以本分支交付摘要为准。
