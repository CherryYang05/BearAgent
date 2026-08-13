---
title: "Implementation Plan: Unified Tool registry, executor, and fixed P1 policy"
status: completed
plan_id: PLAN-F-0006
related_spec: F-0006
created: 2026-08-13
last_updated: 2026-08-14
---

# PLAN-F-0006：统一 Tool Registry、Executor 和 P1 固定 Policy

关联 Spec：`docs/specs/F-0006-tool-registry-executor-policy.md`

## 开始前确认

- 项目所有者已于 2026-08-14 接受 F-0006 Spec；
- 已有 ADR 已经确定三条边界：模型不能给自己授权、不能在宿主 Runtime 执行 shell、核心模块只交换
  BearAgent 数据；
- 仓库目前没有其他 `active` Plan；
- 当前分支是 `codex/F-0006-tool-executor-policy`，从 `main@8ac43f1` 创建。

## 实施步骤

### 第 1 步：先定义门口收什么、返回什么

Status：completed。

完成后，代码会明确回答：一个 Tool 怎样介绍自己，一次请求包含什么，一次成功或失败怎样返回。

- 修改 `domain/tools.py` 和 `domain/errors.py`，让名称、参数、timeout、结果大小和错误都有明确限制；
- 修改 `ports/tools.py`，增加“先检查参数，再执行”的接口；
- 新增 `ports/policy.py`，只规定 Policy 怎样返回允许或拒绝；
- 把新类型加入公共 Schema；
- 测试非法输入、深层数据、事后修改、成功/失败互斥和错误信息安全。

完成标志：Tool 数据测试和公共 Schema 测试通过。此时还不会执行任何真实 Tool。

验证：`uv run pytest tests/unit/test_tool_contracts.py tests/contract/test_domain_schemas.py`

### 第 2 步：建立名单和权限门

Status：completed。

完成后，Runtime 能精确找到已注册 Tool，并能在执行前作出固定的允许或拒绝决定。

- 新增 `runtime/tool_registry.py`：拒绝重名，按名称稳定排序，只做精确查找；
- 新增 `runtime/policy.py`：默认拒绝，只允许程序启动时给出的名称；
- 即使名称在允许名单里，P1 也拒绝外部写入和代码执行；
- 测试外部代码事后修改名单、模型参数伪造权限和危险类别绕过。

完成标志：Registry 单元测试和 Policy 安全测试通过。此时仍未调用 Tool。

验证：`uv run pytest tests/unit/test_tool_registry.py tests/security/test_tool_policy.py`

### 第 3 步：把检查、权限和执行串起来

Status：completed。

完成后，一次请求会真正走完 `查名单 -> 检查参数 -> 检查权限 -> 限时执行`。

- 新增 `runtime/tool_executor.py`；
- 升级测试 Tool，使它能记录每一步是否被调用，并模拟成功、失败、timeout、异常和超大结果；
- 参数错误或权限拒绝时，测试确认执行方法从未运行；
- Tool 已开始后，测试确认每个请求最多调用一次，取消不会被包装成普通失败；
- 任何错误都只能返回有限、安全的信息。

完成标志：Tool 共用接口、Executor 集成测试和安全测试通过。F-0007/F-0008 以后只能通过这个入口
接入真实文件 Tool。

验证：`uv run pytest tests/contract/test_tool_contract.py tests/integration/test_tool_executor.py tests/security/test_tool_executor.py`

### 第 4 步：让读者能看懂已经完成了什么

Status：completed。

- 在站点初学者页用一次 Tool 请求讲清四个步骤；
- 在开发者页标出代码入口和最有用的测试；
- 更新架构、Roadmap 和当前状态；
- 明确写出“已有统一 Tool 路径，但还没有真实文件 Tool、Agent Loop、CLI 或恢复”；
- 运行完整测试、文档链接检查、站点构建和安装包检查。

完成标志：代码、测试、`docs/` 和站点说的是同一件事，Spec 变为 `implemented`，Plan 变为
`completed`。

验证：运行本 Plan 末尾列出的完整命令。

## 每一步都要检查

- [x] 没有绕过 Policy 的执行路径；
- [x] 参数在权限判断前已经检查和规范化；
- [x] timeout、取消、输入/输出上限和单次调用规则有测试；
- [x] 错误没有泄漏原始异常、密钥或完整输出；
- [x] 没有修改 SQLite 或 v1 Event；
- [x] 工程文档、初学者页、开发者页和当前状态同步。

## 最终验证

```powershell
$env:UV_CACHE_DIR = 'D:\BearAgent\.uv-cache'
uv lock --check
uv run ruff check src tests scripts/check_docs.py
uv run ruff format --check src tests scripts/check_docs.py
uv run pyright src tests scripts/check_docs.py
uv run pytest --basetemp D:\BearAgent\.test-tmp\pytest
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
uv build
git diff --check
```

命令没有实际通过前，不得把 Plan 标记为 `completed`，也不得把 Spec 标记为 `implemented`。

2026-08-14 实际结果：`uv lock --check`、Ruff、Pyright、160 项 pytest、63 个 Markdown 文件链接、
Starlight 26 页构建、sdist/wheel 构建、wheel 新公开类型导入和 `git diff --check` 全部通过。站点构建
仍显示既有的 chunk size、缺少 `site` 配置和 `Entry docs -> 404` 警告，但命令成功退出，F-0006
没有新增部署入口。

当前限制：Registry、固定 Policy 和 Executor 已实现，但没有真实文件 Tool、Agent Loop、Tool Event
接线或 CLI Run；这些仍属于 F-0007、F-0008、F-0016 和 F-0005。
