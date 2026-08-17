---
title: "Implementation Plan: Bounded read-only workspace tools"
status: completed
plan_id: PLAN-F-0007
related_spec: F-0007
created: 2026-08-16
last_updated: 2026-08-16
---

# PLAN-F-0007：实现有界的 workspace 只读 Tool

关联 Spec：`docs/specs/F-0007-workspace-read-tools.md`

## 开始前确认

- 项目所有者已于 2026-08-16 接受 F-0007 Spec，并解决其中三个开放问题；
- ADR-0011 已于 2026-08-16 变为 `accepted`；
- F-0006 已合入 `main`，当前分支 `codex/F-0007-workspace-read-tools` 以合并提交
  `main@f07ba07` 为直接基线；
- 激活本 Plan 时，仓库没有其他 `active` Plan；完成后仓库重新回到没有活动 Plan 的状态。

## 实施步骤

### 第 1 步：固定公共失败语言和纯路径规则

Status：completed。

- 交付结果：增加 workspace ErrorCode；把模型路径整理成唯一、可移植的相对路径，非法写法无需访问
  文件系统就能拒绝；
- 代码落点：`domain/errors.py`、`adapters/tools/workspace_boundary.py` 和公共 Schema 快照；
- 接入关系：三个 Tool 的 `prepare` 只调用纯规范化函数；Runtime 仍只接收 `PreparedToolRequest`；
- 重点测试：路径矩阵、不可变参数、错误类别、公共 Schema 快照；
- 验证命令：
  `uv run pytest tests/unit/test_workspace_paths.py tests/contract/test_domain_schemas.py`；
- 回退方式：删除新错误码和纯辅助模块，恢复 Schema 快照；不涉及文件或数据库迁移。

### 第 2 步：建立唯一的真实文件边界

Status：completed。

- 交付结果：固定 workspace 根目录；只解析普通目录/文件；拒绝 symlink、junction、reparse 跳转和
  特殊文件；打开文件后核对对象身份；
- 代码落点：`adapters/tools/workspace_boundary.py`；低层异常只在 adapter 内部使用，转换为有限
  `ErrorInfo`；
- 接入关系：list/read/search 组合同一个 boundary 实例，不各自复制路径规则；
- 重点测试：根目录不合法、向内/向外链接、平台设备名、文件替换、权限异常和绝对路径脱敏；
- 验证命令：
  `uv run pytest tests/unit/test_workspace_boundary.py tests/security/test_workspace_tools.py`；
- 回退方式：删除 adapter 边界组件；没有外部状态。

### 第 3 步：分别实现 list、read 和 search

Status：completed。

- 交付结果：一层稳定分页目录、按完整行分段 UTF-8 读取、有界普通字符串递归搜索；
- 代码落点：`adapters/tools/workspace_list.py`、`workspace_read.py`、
  `workspace_search.py`、`adapters/tools/__init__.py`；
- 接入关系：三个类都只实现已有 `ports.tools.Tool`，共享 boundary，不互相调用；工厂只负责构造，
  不持有 Runtime 或 Policy；
- 重点测试：输入/输出 schema、稳定排序、分页续读、UTF-8 边界、长行、非文本、搜索大小/数量/deadline
  上限和跳过计数；
- 验证命令：
  `uv run pytest tests/unit/test_workspace_list.py tests/unit/test_workspace_read.py tests/unit/test_workspace_search.py tests/contract/test_workspace_tools.py`；
- 回退方式：逐个删除 Tool；共享 boundary 和公共错误可以独立保留到最后。

### 第 4 步：证明所有真实读取都经过 F-0006 入口

Status：completed。

- 交付结果：三个 Tool 在 `ToolRegistry + FixedToolPolicy + ToolExecutor` 下工作；默认拒绝、参数错误、
  timeout、取消、结果超限和异常脱敏保持原契约；
- 代码落点：主要是 `tests/integration/test_workspace_tools.py`、
  `tests/security/test_workspace_tools.py`；若实现暴露 F-0006 缺陷，只做维持既有契约的窄修复；
- 接入关系：测试调用 Executor，而不是把 adapter 直接暴露给模型；不接 Agent Loop 或 CLI；
- 重点测试：不在 allowlist 时零文件访问；Policy 看到规范化路径；一次请求最多执行一次；Prompt/文件
  内容不能扩大权限；取消原样传播；
- 验证命令：
  `uv run pytest tests/integration/test_workspace_tools.py tests/security/test_workspace_tools.py tests/integration/test_tool_executor.py tests/security/test_tool_executor.py`；
- 回退方式：移除真实 Tool 注册工厂和集成测试，不修改 F-0006 公共路径。

### 第 5 步：用读者问题收束文档和完整验证

Status：completed。

- 交付结果：工程事实、初学者页、开发者入口和当前状态一致；Spec/ADR/Plan 只在命令实际通过后关闭；
- 代码落点：相关 `docs/`、`site/src/content/docs/zh-cn/learn/`、
  `site/src/content/docs/zh-cn/development/` 和 `site/src/content/docs/zh-cn/project/status.md`；
- 接入关系：学习页从“为什么不能直接打开模型给的路径”开始；开发者页再说明 boundary 和三个 Tool；
- 重点测试：链接检查、站点构建、wheel 导入和 `git diff --check`；
- 验证命令：运行本 Plan 的最终验证；
- 回退方式：文档与实现一起回退，状态页不能留下已实现声明。

## 关键注释原则

只在代码本身不能说明“为什么”时写注释，至少覆盖下面三处：

- `prepare` 的路径检查旁说明为什么这里不能做文件系统 I/O；
- 不跟随链接和文件身份复核处说明防止的是哪一种检查/打开不一致；
- 搜索遍历处说明为什么不用会隐式跟随或假设目录不变的便利 API，以及每个硬上限在哪里生效。

普通参数赋值、明显的排序和测试步骤不写逐行翻译式注释。公开类和关键函数使用简短 docstring 说明
职责与边界，不在代码里复制整篇 Spec。

## 每一步都要检查

- [x] 不增加持久化、Event 或恢复声明；
- [x] 根目录只能由可信构造代码提供，所有实际读取经过统一 Policy 和 Executor；
- [x] timeout、取消、文件/目录/行/搜索/输出限制均有测试；
- [x] ErrorInfo、日志和 ToolResult 不出现绝对路径、链接目标或原始异常；
- [x] 不增加 migration、生产依赖、shell 或网络入口；
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
uv run pytest --basetemp=.pytest_cache/f0007-final
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
uv build
git diff --check
```

还要从构建出的 wheel 导入三个 workspace Tool 和新增 ErrorCode，确认打包没有漏文件。命令没有实际
通过前，不得把 Plan 标记为 `completed` 或把 Spec 标记为 `implemented`；ADR 的 `accepted` 只表示
决定已经生效，不表示实现完成。

2026-08-16 实际结果：`uv lock --check`、Ruff、Pyright、pytest 203 项通过且 1 项跳过、86 个
Markdown 文件链接、Starlight 28 页构建、sdist/wheel 构建、wheel 隔离导入和 `git diff --check`
均通过。Windows 当前用户
没有创建 symlink 的权限，因此实际 symlink 用例跳过；junction 分类、最终对象替换和所有路径字符串
拒绝在 Windows 通过，symlink 用例会在支持该能力的 Ubuntu CI 中运行。
