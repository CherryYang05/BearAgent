---
title: "Implementation Plan: Atomic output writing and Artifact metadata"
status: completed
plan_id: PLAN-F-0008
related_spec: F-0008
created: 2026-08-17
last_updated: 2026-08-17
---

# PLAN-F-0008：实现 outputs 原子写入和 Artifact 元数据

关联 Spec：`docs/specs/F-0008-atomic-output-artifacts.md`

## 开始前确认

- [x] 项目所有者于 2026-08-17 接受 F-0008 Spec；
- [x] 项目所有者于 2026-08-17 接受 ADR-0012 的原子提交、失败和保留规则；
- [x] F-0008 Spec 第 16 节的五项决定全部解决；
- [x] F-0006/F-0007 已合入 `main@66338ac`；
- [x] 当前分支是从该提交创建的 `codex/F-0008-atomic-output-artifacts`；
- [x] 仓库没有其他 `active` 主 Plan；
- [x] 以上条件满足，本 Plan 于 2026-08-17 从 `draft` 改为 `active`。

## 实施步骤

### 第 1 步：建立可序列化的 Artifact 契约

Status：completed。

- 交付结果：新增冻结 `Artifact` 与有限枚举，严格校验 UUID4、有限非空路径、text/UTF-8、
  size_bytes 和 64 位小写 SHA-256；路径只是元数据，不单独授予文件访问权限；
- 代码落点：`src/bearagent/domain/artifacts.py`、`domain/__init__.py`、`domain/schema.py` 和公共 Schema
  快照；
- 接入关系：workspace adapter 构造 Artifact；Runtime、Provider 和 Store 只看到 BearAgent 类型；
- 重点测试：未知字段、非法 hash/size/空路径/type/encoding、冻结性、JSON round-trip 和 Schema 快照；
- 验证命令：
  `uv run pytest tests/unit/test_artifacts.py tests/contract/test_domain_schemas.py`；
- 回退方式：删除尚未被 Event/SQLite 使用的 Artifact 类型并恢复 Schema 快照。

### 第 2 步：扩展 workspace 边界并实现原子写入 Tool

Status：completed。

- 交付结果：`workspace.write` 只接收 `outputs/<file>` 和有限 UTF-8 文本；在 Policy 后创建安全父目录，
  同目录暂存、`fsync`、复核 deadline/路径，再执行一次 `os.replace`；
- 代码落点：`adapters/tools/workspace_boundary.py`、新增 `workspace_write.py`，以及必要的限制常量和共享
  结果 helper；
- 接入关系：写入 Tool 实现已有 `ports.tools.Tool`，复用 F-0007 路径规则，不修改 Tool port，也不让
  Runtime 导入 adapter；
- 重点测试：创建/替换、嵌套父目录、UTF-8 原样 bytes、空内容、512 KiB/单行边界、hash、链接、特殊
  文件、已有目标类型和临时文件清理；
- 验证命令：
  `uv run pytest tests/unit/test_artifacts.py tests/unit/test_workspace_write.py tests/unit/test_workspace_boundary.py`；
- 回退方式：移除写入方法和 Tool；只读路径行为保持不变，没有数据库状态。

### 第 3 步：让四个 workspace Tool 经过同一个执行入口

Status：completed。

- 交付结果：保留 `build_workspace_read_tools` 兼容入口，新增共享一个 `WorkspaceBoundary` 的四 Tool
  工厂；写入 Tool 只有名称在可信 allowlist 时才能执行；
- 代码落点：`adapters/tools/__init__.py`、Policy/Executor 测试和 workspace contract/integration tests；
- 接入关系：Registry 保存可信 `WORKSPACE_WRITE/NOT_SAFE` Spec；Policy 保持默认拒绝，Executor 继续
  按 `prepare -> Policy -> execute` 调用一次；
- 重点测试：Policy 看见规范化 `outputs/**`；未 allowlist、参数失败和 Policy 拒绝时零目录/文件改动；
  成功结果关联原 ToolCallId；read 能读回 write 的完整结果；
- 验证命令：
  `uv run pytest tests/contract/test_workspace_tools.py tests/integration/test_workspace_tools.py tests/security/test_tool_policy.py tests/integration/test_tool_executor.py`；
- 回退方式：移除四 Tool 工厂和写入集成用例，保留现有只读工厂。

### 第 4 步：用故障注入证明不会暴露半份目标

Status：completed。

- 交付结果：在目录创建、暂存写、`fsync`、类型复核和 replace 处确定性注入失败；正常异常路径清理
  临时文件，旧目标不变；timeout/取消不自动重试；
- 代码落点：实现只增加最小测试 seam，主要证据放在 `tests/security/test_workspace_write.py` 和
  `tests/integration/test_workspace_tools.py`；
- 接入关系：故障转换成有限 `ToolResult/ErrorInfo`；不修改 Event、Reducer、SQLite 或恢复状态；
- 重点测试：replace 前各失败点、目标/父目录检查后替换、绝对路径脱敏、临时名脱敏、Prompt 提权、
  超大输入和 Executor timeout/cancel；Windows 无链接权限时延续 F-0007 的确定性分类模拟；
- 验证命令：
  `uv run pytest tests/security/test_workspace_write.py tests/security/test_workspace_tools.py tests/security/test_tool_executor.py`；
- 回退方式：删除测试 seam 与写入实现；不触碰用户现有 `outputs/**`。

### 第 5 步：同步四个文档表面并完成完整验证

Status：completed。

- 交付结果：工程 Spec/ADR/Plan/Architecture/Roadmap、站点初学者页、开发者页和当前状态一致；
  `.gitignore` 忽略 BearAgent 仓库根目录演示产物；只有命令实际通过后关闭 Feature；
- 代码落点：相关 `docs/`、`site/src/content/docs/zh-cn/learn/`、
  `site/src/content/docs/zh-cn/development/`、`site/src/content/docs/zh-cn/project/status.md`、README 和
  `.gitignore`；
- 接入关系：学习页从“为什么不能直接覆盖 intro.md”开始；开发者页说明暂存、replace、Artifact 和
  崩溃窗口；状态页明确还没有 Agent Loop/Event/CLI；
- 重点测试：文档链接、站点构建、公共 Schema、wheel 导入、`git diff --check` 和完整质量检查；
- 验证命令：运行本 Plan 的最终验证；
- 回退方式：文档与实现一起回退，不能删除用户已经生成的 Artifact。

## 关键注释原则

只在代码本身不能说明“为什么”时写注释，至少覆盖：

- 临时文件必须在目标目录：保持同一文件系统，让 replace 成为唯一提交点；
- `fsync` 与 replace 之间复核 deadline/路径：timeout 不会撤销外部副作用；
- 最终同步 replace 不跨 `await`：避免线程取消后在后台继续提交。

普通参数赋值、hash 调用和 Pydantic 字段不写逐行翻译式注释。公开类型和关键函数只用简短 docstring
说明职责与边界。

## 每一步都要检查

- [x] Artifact 只通过 ToolResult 产生，F-0008 不新增 Event、projection 或 migration；
- [x] 所有文件改动经过 Registry、prepare、固定 Policy 和 Executor；
- [x] timeout、取消、内容/单行/路径/输入/结果上限都有测试；
- [x] replace 前失败保持旧目标，replace 后不谎称具备 P2 恢复；
- [x] ErrorInfo、日志和 ToolResult 不包含绝对路径、临时名、原始异常、秘密或完整 content；
- [x] 不增加生产依赖、shell、网络、自动重试、后台清理或 delete Tool；
- [x] `domain`、`ports`、`runtime` 不导入 workspace adapter；
- [x] 工程文档同步；
- [x] 站点初学者路径同步；
- [x] 站点开发者文档同步；
- [x] 站点当前状态同步。

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

还要从 wheel 导入 `Artifact`、`WorkspaceWriteTool` 和四 Tool 工厂，并在 Windows/Ubuntu 核对相同
写入与故障测试。命令未通过前，不得把 Plan 标为 `completed`、Spec 标为 `implemented`，也不能把
站点写成“Agent 已能完成文件任务”。

2026-08-17 实际结果：`uv lock --check`、Ruff、格式检查、Pyright、pytest 245 项、72 个 Markdown
文件链接、公共 Schema 重生成稳定、Starlight 30 页构建、sdist/wheel 构建、wheel 隔离导入和
`git diff --check` 均通过。Windows 测试覆盖创建、替换、精确内容/单行上限、默认拒绝、目录与临时
文件故障、`fsync`/replace 故障、对象替换、timeout 和取消；真实 symlink 用例继续由 Ubuntu CI
验证，Windows 通过确定性 link/junction 分类覆盖相同拒绝分支。
