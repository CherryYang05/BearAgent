---
title: "Implementation Plan: Bounded context and serial Agent Loop"
status: completed
plan_id: PLAN-F-0016
related_spec: F-0016
created: 2026-08-18
last_updated: 2026-08-20
---

# PLAN-F-0016：实现有界 Context 和串行 Agent Loop

关联 Spec：`docs/specs/F-0016-bounded-context-agent-loop.md`

## 开始前确认

- [x] 项目所有者于 2026-08-18 选择 F-0016 作为下一个 Feature；
- [x] 项目所有者于 2026-08-18 接受 F-0016 Spec；
- [x] 项目所有者于 2026-08-18 接受 ADR-0013 的串行执行、Event 边界和 v2 兼容决定；
- [x] F-0016 Spec 第 16 节的五项决定全部解决；
- [x] F-0004/F-0006/F-0007/F-0008 已合入 `main@146f24a`；
- [x] 当前分支是从该提交创建的 `codex/F-0016-agent-loop`；
- [x] 仓库没有其他 `active` 主 Plan；
- [x] 以上条件满足，本 Plan 于 2026-08-18 从 `draft` 改为 `active`。

## 实施步骤

### 第 1 步：建立配置、Context 报告、执行记录和 v2 Event 契约

Status：completed（2026-08-18）。

- 交付结果：新增冻结有界 AgentConfig/定价/Context 报告/Run 输入结果/Tool 执行记录；为同名 Run 与
  Activity Event 增加 v2 payload，v1 继续原样解析；
- 代码落点：`src/bearagent/domain/`、`domain/schema.py`、`runtime/reducer.py` 和公共 Schema 快照；
- 接入关系：application/Runtime 只交换 BearAgent 类型；Reducer 从 v1/v2 共有状态字段产生同一 projection；
- 重点测试：[AC-7][AC-8][AC-9] 严格字段、深层不可变、大小/版本/费率边界、v1/v2 重放、敏感字段拒绝；
- 验证命令：
  `uv run pytest tests/unit/test_agent_config.py tests/unit/test_run_reducer.py tests/security/test_run_events.py tests/contract/test_domain_schemas.py`；
- 回退方式：在尚未产生 v2 Event 前移除新类型并恢复 Schema；产生后必须保留 v2 读取兼容。

### 第 2 步：实现只从已提交事实构造请求的 ContextBuilder

Status：completed（2026-08-18）。

- 交付结果：按 Runtime/Agent/目标/历史稳定顺序构造 ModelRequest；ToolSpec 稳定转换；ToolResult preview
  截短与最早完整交互组省略可检查且确定；
- 代码落点：`src/bearagent/runtime/context.py` 及对应 unit/security tests；
- 接入关系：输入是 AgentConfig、Registry specs 和 v2 Event；输出 exact ModelRequest + Context 报告，
  不调用 Provider/Tool/Store adapter；
- 重点测试：[AC-2][AC-8] 稳定顺序、总上限、单结果上限、UTF-8、多 Tool call/result 分组、固定层超限、
  Prompt/ToolResult 不能变成 system authority；
- 验证命令：`uv run pytest tests/unit/test_context_builder.py tests/security/test_context_builder.py`；
- 回退方式：移除尚未被 application 调用的纯组件，不修改历史 Event。

### 第 3 步：让 ToolExecutor 返回可持久化记录但保持单一执行路径

Status：completed（2026-08-18）。

- 交付结果：增加记录式 Tool 执行结果，包含原始/规范化请求、Policy 决定和 ToolResult；现有 `execute`
  行为与契约保持兼容，两入口共用唯一私有实现；
- 代码落点：`runtime/tool_executor.py`、`domain/tools.py` 或独立执行记录模块，以及 executor contract/
  integration/security tests；
- 接入关系：Agent Loop 只调用 ToolExecutor；Executor 仍唯一调用 Tool adapter 与 Policy；
- 重点测试：[AC-4][AC-8] not-found、prepare、Policy deny、timeout、异常、输出超限、取消、身份不匹配和
  allowlist 旁路；
- 验证命令：
  `uv run pytest tests/contract/test_tool_contract.py tests/integration/test_tool_executor.py tests/security/test_tool_executor.py tests/security/test_tool_policy.py`；
- 回退方式：保留现有 execute 公共行为，移除未被 Loop 发布的记录式 API。

### 第 4 步：测试先行实现串行 Agent Loop 和费用记账

Status：completed（2026-08-18）。

- 交付结果：application service 创建 Run、逐 Activity 检查预算、保存 Event、调用 Provider/Executor、
  处理 Tool 反馈和终止；费用按版本化整数费率计算；
- 代码落点：`src/bearagent/application/agent_loop.py`、必要 Runtime 纯 helper，以及 unit/integration/recovery tests；
- 接入关系：Loop 注入 ModelProvider/EventStore/ToolExecutor/clock/ID generator；不导入任何具体 adapter；
- 重点测试：[AC-1][AC-3][AC-5][AC-6][AC-9] 文本终止、多 Tool call、Tool failure 纠正、五维预算、
  Provider/协议失败、每个 append 故障点、timeout、取消和写后存储失败不重试；
- 验证命令：
  `uv run pytest tests/unit/test_agent_loop.py tests/recovery/test_agent_loop_boundaries.py tests/security/test_agent_loop.py`；
- 回退方式：移除 application service；保留已提交 v2 Event 读取兼容，不删除 Artifact。

### 第 5 步：建立五个固定任务并在内存/SQLite 上完成 5/5

Status：completed（2026-08-18）。

- 交付结果：版本化任务 fixture 与逐请求 Fake Provider 脚本，覆盖单文档、多文档、来源比较、替换输出、
  路径/预算失败；两种 Store 与真实 workspace Tool 运行同一关键路径；
- 代码落点：`evals/p1/tasks.json`、`evals/p1/workspaces/`、`adapters/testing/model.py`、`tests/evals/`
  和 integration tests；
- 接入关系：任务通过 application service 运行；不增加 CLI、网络或生产依赖；
- 重点测试：[AC-1][AC-4][AC-7][AC-10] exact Tool 顺序/参数、Event sequence、Artifact hash、确定性终止
  和重开 SQLite 后事实可查；
- 验证命令：`uv run pytest tests/evals tests/integration/test_sqlite_event_store.py`；
- 回退方式：移除任务/Fake 脚本扩展；保留通用 ModelProvider contract。

### 第 6 步：同步四个文档表面并完成完整验证

Status：completed（2026-08-20）。

- 交付结果：工程 Spec/ADR/Plan/Architecture/Roadmap、站点学习页、开发者页和当前状态一致；只有命令
  实际通过后关闭 Feature；
- 代码落点：相关 `docs/`、`site/src/content/docs/zh-cn/learn/`、
  `site/src/content/docs/zh-cn/development/`、`site/src/content/docs/zh-cn/project/status.md` 和索引；
- 接入关系：学习页从一个具体文件任务解释整条链；开发者页说明 Context/v2 Event/故障边界；状态页
  明确 F-0005 CLI、P2 恢复和 P3 Approval/sandbox 未实现；
- 重点测试：[AC-11] 文档链接、站点构建、公共 Schema、wheel 导入、`git diff --check` 和完整质量检查；
- 验证命令：运行本 Plan 的最终验证；
- 回退方式：文档与实现一起回退，不能删除用户 Artifact，也不能删除 v2 Event 兼容读取。

## 耦合评估

- 新增/修改公共接口：新增 AgentConfig、Context 报告、Run application 输入/结果、Tool 执行记录和 v2
  Event payload；ToolExecutor 保留现有 `execute` 兼容；
- 依赖模块：application 依赖 domain/runtime/ports；runtime 依赖 domain/ports；adapters 仍向内实现 ports；
- 新依赖：不增加生产或开发依赖；
- 依赖方向：不允许 domain/runtime/application 导入 OpenAI SDK、SQLite adapter、workspace adapter 或 CLI；
- 循环风险：ContextBuilder 不能依赖 application；ToolExecutor 记录类型放 domain，不能反向依赖 Loop；
- 扇出控制：Agent Loop 只做协调，Event 构造、Context、定价和模型流组装按单一职责拆分，避免上帝文件。

## 关键注释原则

只在代码不能直接说明原因时注释，重点覆盖：

- started Event 必须先提交：外部调用发生前留下持久边界；
- ToolExecutor 两个公共用法必须汇合到同一私有路径：防止 Policy/timeout 旁路；
- Context 以完整交互组为单位省略：保持 Tool call/result 历史合法；
- 写入完成但 terminal Event append 失败时停止且不重试：P1 不伪造 exactly-once/UNKNOWN。

普通字段复制、Event sequence 加一和 Pydantic 构造不写逐行翻译式注释。

## 每一步都要检查

- [x] v1 Event 永久可读，新 Run 只写明确 v2；SQLite 表结构无隐式 migration；
- [x] 所有状态/预算来自 Event + Reducer，不维护第二份可变计数；
- [x] 所有 Tool 外部动作经过 Registry、prepare、固定 Policy 和 ToolExecutor；
- [x] timeout、取消、Context/消息/Tool/结果/Event 上限有明确测试；
- [x] 外部调用后 append 失败保持非终态、不重试、不伪造成功或 UNKNOWN；
- [x] Runtime 不向 Event 元数据、Context 报告、日志和 Error 主动泄露凭据、绝对根、原始异常或临时名；
- [x] domain/runtime/application 没有外层 adapter/SDK/CLI 导入；
- [x] 不增加生产依赖、shell、网络、并行 Tool、自动 retry 或 workflow framework；
- [x] AC 编号与测试/Plan 步骤回链；
- [x] 工程文档、站点初学者路径、开发者文档和当前状态同步。

## 最终验证

```powershell
$env:UV_CACHE_DIR = 'D:\BearAgent\.uv-cache'
uv lock --check
uv run ruff check src tests scripts/check_docs.py
uv run ruff format --check src tests scripts/check_docs.py
uv run pyright src tests scripts/check_docs.py
uv run pytest
uv run python scripts/generate_domain_schemas.py
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
uv build
git diff --check
```

还要从构建 wheel 隔离导入 F-0016 新公共类型与 application service，并在 Windows/Ubuntu 运行相同的
Event/Context/Loop/Tool 安全测试。命令没有实际通过前，不得把 Plan 标记为 `completed`、Spec 标记为
`implemented`，也不能把站点写成“用户已经可以运行 CLI 文件任务”。

本地 Windows 收尾结果：319 tests、Ruff、format、Pyright、84 个 Markdown 链接、32 页 Starlight、
sdist/wheel、隔离 wheel 导入和 diff 检查通过；PR CI 继续在 Ubuntu 重跑同一默认测试集。站点仍明确
生产 CLI、P2 恢复和 P3 Approval/sandbox 未实现。
