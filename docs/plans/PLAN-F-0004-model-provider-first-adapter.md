---
title: "Implementation Plan: ModelProvider internal interface and first production adapter"
status: completed
plan_id: PLAN-F-0004
related_spec: F-0004
created: 2026-08-13
last_updated: 2026-08-13
---

# Implementation Plan: ModelProvider 内部接口与首个生产适配器

Related Spec: `docs/specs/F-0004-model-provider-first-adapter.md`

## Preconditions

- F-0004 status is `accepted`.
- ADR-0007 and ADR-0010 are `accepted`.
- F-0004 open questions are resolved.
- No other main Implementation Plan is `active`.

所有前置条件已于 2026-08-13 满足。

## 可单独完成和测试的实现步骤

### 第一步：定义模型调用的内部数据格式与规则

- Status：completed。
- 内部数据与规则：定义有大小限制的 `ModelRequest`/Tool、按 `kind` 区分的流事件、用量、
  响应信息和安全错误。
- 接口与外部实现：升级 `ModelProvider` 内部接口的公开类型与模型服务替代实现；暂不接生产 SDK。
- 测试：数据格式、不可修改性、大小限制、预设成功/失败流和公共 JSON Schema 快照。
- Verification command：`uv run pytest tests/unit/test_model_contracts.py tests/unit/test_testing_adapters.py tests/contract/test_domain_schemas.py`。
- 安全回退点：恢复 P0 dataclass 模型类型；无持久化或外部调用。

### 第二步：接入并翻译 OpenAI Responses 流

- Status：completed。
- 内部数据与规则：不新增 OpenAI 专用的内部类型；固定完成事件、工具调用与错误规则。
- 接口与外部实现：使用官方异步 SDK，允许测试注入客户端，翻译请求/事件，设置有限超时且不自动重试。
- 测试：文本、工具调用、用量、损坏/中途失败的流、取消传播与错误分类。
- Verification command：`uv run pytest tests/contract/test_model_provider_contract.py tests/security/test_model_provider.py`。
- 安全回退点：删除 SDK 与生产适配器；Fake 和内部接口仍可使用。

### 第三步：同步文档并关闭 Feature

- Status：completed。
- 内部数据与规则：审查 SDK 没有进入 core；确认 F-0016 能接收完成信息与用量。
- 接口与外部实现：同步公开导出、安装包、Spec、ADR、架构与索引。
- Tests：完整 DoD、docs link、Starlight build 与 wheel import。
- Verification command：见 Final verification。
- 安全回退点：F-0016 开始前可整体回退 F-0004；没有数据库迁移。

## 跨步骤检查

- [x] 持久化/恢复：流式响应中途失败不伪造成功；F-0004 不追加 Event，也不自动重试。
- [x] 权限/安全：隔离 SDK、校验模型服务商输出、错误不泄漏敏感信息。
- [x] 超时/取消/资源限制：有限请求超时、取消传播、输入/输出上限。
- [x] 日志/执行记录/指标：模型完成信息可供 F-0016 持久化；本 Feature 不加后端。
- [x] 迁移/回退：无需迁移数据；依赖和适配器可整体回退。
- [x] 工程文档已同步
- [x] 站点初学者学习路径已同步
- [x] 站点开发者文档已同步
- [x] 站点当前状态与阶段总结已同步

## Final verification

```powershell
$env:UV_CACHE_DIR = 'D:\BearAgent\.uv-cache'
uv lock --check
uv run ruff check src tests scripts/check_docs.py
uv run ruff format --check src tests scripts/check_docs.py
uv run pyright src tests scripts/check_docs.py
uv run pytest
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
uv build
git diff --check
```

2026-08-13 实际结果：锁文件有效；Ruff 与 Pyright 通过；130 项 pytest 通过；58 个 Markdown
文件的本地链接通过；Starlight 生成 23 页；source distribution 与 wheel 构建成功，且 wheel 在
临时隔离环境中可以导入 `OpenAIResponsesProvider` 与 `ModelRequest`；`git diff --check` 通过。

验证明确排除未跟踪、且不属于 F-0004 的 `scripts/demo_reducer.py`；该文件自身存在既有 Ruff/
Pyright 问题，本 Plan 没有修改或纳入它。共用接口测试在无网络/API key 下覆盖模型服务替代实现
与注入式 OpenAI 流；核心代码不导入 SDK；错误/响应不泄漏密钥；站点明确 F-0004 只实现模型
边界，尚没有 Agent Loop、Tool 执行、CLI Run 或崩溃恢复能力。
