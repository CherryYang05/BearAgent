---
title: "Implementation Plan: configurable model service protocols and P1 live-model gate"
status: completed
plan_id: PLAN-F-0017
related_spec: F-0017
created: 2026-08-22
last_updated: 2026-08-23
---

# PLAN-F-0017：配置模型服务协议并完成 P1 真实模型 gate

关联 Spec：`docs/specs/F-0017-configurable-model-providers-live-gate.md`

## 开始前确认

- [x] 项目所有者于 2026-08-22 接受 F-0017 Spec，status 已从 `draft` 改为 `accepted`；
- [x] 项目所有者同时接受 ADR-0015，status 已从 `proposed` 改为 `accepted`；
- [x] 当前分支 `codex/F-0017-p1-live-model-gate` 从 `main@17a3a92` 创建；
- [x] 仓库没有其他 `active` 主 Plan；
- [x] 真实 model、定价快照和费用上限延后到 live preflight 前确认，不阻塞离线实现；
- [x] 真实 gate 通过后提交脱敏 report，不提交完整输出、Event、endpoint 或 secret；
- [x] 以上条件满足，本 Plan 于 2026-08-22 从 `draft` 激活为 `active`。

## 实施步骤

### 第 1 步：冻结 BearAgent config、RunProfile v2 和安全读取边界

Status：completed（2026-08-22）。

- 交付结果：新增严格 config v1 和 `RunProfile v2.provider_id`；config 保存厂商显示名、显式 model 列表和
  默认 model，拒绝 pricing；RunProfile v2 不重复保存 model/pricing；v1 legacy Responses 继续可读；
  config/profile 均使用有界普通文件读取，key 由 config 的 `SecretStr` 字段直接提供；
- 代码落点：`src/bearagent/domain/agent.py`、独立外层配置模块、`data/` 示例、公共 Schema 与
  unit/security tests；
- 接入关系：CLI/bootstrap 读取 profile 和 catalog；只有选中的配置进入 composition，base URL、
  key 不进入 AgentConfig、Runtime 或 Tool；
- 重点测试：[AC-1][AC-3][AC-5] v1/v2、未知字段、重复 ID、文件大小/UTF-8/link/TOCTOU、URL、直接 key、`SecretStr`、
  配置复用和 secret redaction；
- 验证命令：`uv run pytest tests/unit/test_agent_config.py tests/unit/test_provider_config.py tests/security/test_provider_config.py`；
- 回退方式：移除尚未接入 production 的 catalog/v2 类型并恢复 Schema；保留 v1 行为和用户文件。

#### 2026-08-23 本地凭证可用性调整

项目所有者确认 P1 本地配置直接填写 API key，不再要求额外创建环境变量。Config 使用 `SecretStr`、
隐藏校验输入并保持 `data/config.json` 被 Git 忽略；普通 CLI 只读取这一份本机文件。Live preflight
冻结 config 后以内存对象复用 production factory，不再写第二份临时 key 文件。

#### 2026-08-23 config 文件名与字段复核

项目所有者要求 Provider 配置采用当前 Agent 工具的常见字段。对照 OpenCode、Continue、Cline、
OpenHands 和 Aider 官方文档后，本步骤在同日重新打开：公开文件统一为 `data/config.json`，CLI 使用
`--config`；配置保留 Provider、protocol、HTTPS base URL、直接 API key、模型集合和默认模型，明确拒绝
`pricing`。普通 Run 使用 `unpriced`，真实 gate 单独接收价格快照和费用上限；非密钥 `config_version`
仍由程序计算。在线模型发现后置，因为普通自定义云端 Provider 没有统一、可靠的自动发现契约。
### 第 2 步：用 Event v3 保存有限 Provider selection

Status：completed（2026-08-22）。

- 交付结果：新增冻结的 `ProviderSelection` 和 `RunCreated v3` payload；新 Run 保存 `provider_id`、
  由非密钥 Provider/model 字段计算的 `config_version`、`protocol`，旧 Event v1/v2、Reducer 和
  SQLite schema v1 继续可读；
- 代码落点：`src/bearagent/domain/run_events.py`、`events.py`、`runs.py`、`schema.py`、AgentLoop/query
  和 domain/contract/recovery/security tests；
- 接入关系：bootstrap 把有限 selection 交给 application；AgentLoop 只写 Event；Reducer/query 只解析展示，
  不按 protocol 分支；
- 重点测试：[AC-5][AC-6] v1/v2/v3 读取、冻结/未知字段、projection 重开、inspect/events 脱敏、无 SQL migration；
- 验证命令：`uv run pytest tests/unit/test_events.py tests/unit/test_run_reducer.py tests/contract/test_domain_schemas.py tests/recovery tests/security/test_run_events.py`；
- 回退方式：Event v3 尚未写入前可移除；一旦产生 v3，必须永久保留读取兼容，不删除数据库或 Artifact。

### 第 3 步：收紧共享 ModelProvider contract 和现有 Responses adapter

Status：completed（2026-08-23）。

- 交付结果：把文本、单/多 ToolCall、usage、finish、request identity、错误、timeout、cancel、no-retry
  固化为所有生产 adapter 的共享 contract；现有 Responses 行为与严格未知事件边界一致；
- 代码落点：`tests/contract/test_model_provider_contract.py`、`tests/security/test_model_provider.py`、
  `src/bearagent/adapters/model/openai_responses.py` 和有限共享 helper；
- 接入关系：adapter 只翻译 `ModelRequest`/`ModelEvent`；不追加 Event、不执行 Tool、不读取 BearAgent config；
- 重点测试：[AC-4][AC-5][AC-8] 完整多 ToolCall、缺 usage、ToolCall 改变、重复/缺 completion、未知关键 event、
  stream 后事件、取消和 SDK 原始错误脱敏；
- 验证命令：`uv run pytest tests/contract/test_model_provider_contract.py tests/security/test_model_provider.py`；
- 回退方式：保留原有 Responses 契约，移除未被新 adapter 使用的共享 helper，不改变 Runtime port。

### 第 4 步：实现 OpenAI Chat Completions adapter

Status：completed（2026-08-23）。

- 交付结果：使用现有 OpenAI SDK 实现 `openai_chat_completions` 流式翻译，支持严格受测文本、单/多
  ToolCall、usage、finish 和安全错误；自动重试关闭；
- 代码落点：`src/bearagent/adapters/model/openai_chat_completions.py`、adapter export、mock transport/
  contract/integration/security tests；
- 接入关系：实现既有 `ModelProvider` port；SDK 类型只停留在 `adapters/model/`；
- 重点测试：[AC-2][AC-4][AC-5][AC-8] chunk 重组、index/ID/arguments 不一致、parallel ToolCall 完整翻译、
  include usage、timeout/cancel/no-retry 和原始响应不泄漏；
- 验证命令：`uv run pytest tests/contract/test_model_provider_contract.py tests/integration/test_model_adapters.py tests/security/test_model_provider.py`；
- 回退方式：从 factory/export 移除 Chat adapter；不修改 Event、Run 或 Responses adapter 语义。

2026-08-23 的第一次 DeepSeek 真实 gate 暴露了两个协议兼容问题：内部 Tool 名称中的 `.` 不符合 Chat
Completions function name 约束；DeepSeek V4 默认 thinking 的 Tool 往返需要回放 `reasoning_content`。修复把
Tool wire 别名映射留在 adapter 边界，并在 model 配置中加入显式 `thinking_mode: "disabled"`。BearAgent
不保存隐藏推理；收到无法安全表示的非空 reasoning 时返回协议错误。标准端点也不依赖 Provider 的
`strict` 扩展，Tool 参数继续由 BearAgent 自己校验。失败 attempt 保留为本地证据，修复后另建 attempt。

### 第 5 步：实现 Anthropic Messages adapter 和有界依赖

Status：completed（2026-08-23）。

- 交付结果：加入锁定兼容版本的官方 Anthropic Python SDK，关闭自动重试，实现 `anthropic_messages`
  文本、单/多 ToolUse、usage、stop reason、request identity 和安全错误翻译；
- 代码落点：`pyproject.toml`、由 `uv` 生成的 `uv.lock`、`src/bearagent/adapters/model/anthropic_messages.py`、
  adapter export 与 mock transport/contract/security tests；
- 接入关系：Messages adapter 只实现 `ModelProvider` port；domain/runtime/application 不导入 Anthropic SDK；
- 重点测试：[AC-2][AC-4][AC-5][AC-8] content block 生命周期、ToolUse JSON object、usage、stop、缺失/
  未知事件、timeout/cancel/no-retry、依赖和 import boundary；
- 验证命令：`uv lock --check` 与 `uv run pytest tests/contract/test_model_provider_contract.py tests/integration/test_model_adapters.py tests/security/test_model_provider.py tests/architecture/test_import_boundaries.py`；
- 回退方式：先移除 factory/export/adapter，再用 `uv` 删除 Anthropic 依赖；不得手工编辑 lockfile。

### 第 6 步：在 bootstrap/CLI 接通显式 protocol selection

Status：completed（2026-08-23）。

- 交付结果：唯一 production factory 按三个精确 protocol 创建 lazy adapter；`bearagent run` 默认读取
  `data/config.json` 并支持 `--config`；bootstrap 从默认 model 构造内部完整 `AgentConfig`；
  缺 key/Provider/model 配置在数据库和 Run 创建前安全失败且无 fallback；
- 代码落点：`src/bearagent/bootstrap.py`、`interfaces/cli/`、exports/examples/generated CLI Schema 和
  unit/integration/security/architecture tests；
- 接入关系：CLI 只传路径；bootstrap 选择 adapter；application/runtime/domain 不认识 SDK、endpoint 或厂商；
- 重点测试：[AC-1][AC-2][AC-3][AC-5][AC-9] 三协议选择、legacy v1、未知引用、lazy key、零预算零 client、
  无探测/fallback、生产路径不可注入厂商参数；
- 验证命令：`uv run pytest tests/unit/test_bootstrap.py tests/unit/test_cli.py tests/integration/test_run_cli.py tests/security/test_cli_boundaries.py tests/architecture/test_import_boundaries.py`；
- 回退方式：CLI 暂停暴露 v2/catalog 并恢复 legacy Responses composition；保留 Event v3 读取兼容。

### 第 7 步：实现默认关闭的 P1 live runner、rubric 和脱敏报告

Status：completed（2026-08-23）。

- 交付结果：五个 versioned task 共用 production composition；preflight 在任何副作用前校验 opt-in、配置、
  key、model、定价和费用上限；四个正常任务与强制 canary 由确定性 rubric 判断；每次 attempt 原子写独立 report；
- 代码落点：`evals/p1/`、`scripts/run_p1_live_eval.py`、`.gitignore`、unit/eval/integration/security tests；
- 接入关系：runner 复用 `build_run_services`、AgentLoop、SQLite query 和现有 workspace Tools，不注入
  Fake/Provider，也不复制执行逻辑；
- 重点测试：[AC-9][AC-10][AC-11][AC-12] preflight 零 DB/workspace/client、fixture/rubric 一致、路径 canary、
  SQLite 重开、费用估算、失败不重试、不把 incomplete 写成 passed、report secret 扫描；
- 验证命令：`uv run pytest tests/evals tests/unit/test_p1_live_eval.py tests/integration/test_p1_live_eval.py tests/security/test_p1_live_eval.py`；
- 回退方式：移除 runner/report 实现和未产生的派生证据；不删除任何已创建 Run、数据库或 Artifact。

### 第 8 步：运行离线 Reality Check，同步文档，再单独执行真实 gate

Status：completed（2026-08-23）。

- 交付结果：完整离线质量门通过；suite v1.1.1 经 production composition 使用 DeepSeek V4 完成四个
  普通任务与安全 canary；脱敏报告、工程文档、site beginner、site developer、current status 和 P1
  milestone 一致，F-0017/P1 关闭；
- 代码落点：相关 `docs/`、`site/src/content/docs/zh-cn/`、generated reference、脱敏 report 和 Feature/Plan 状态；
- 接入关系：学习页解释一次配置多次运行；开发者页解释协议 factory/Event v3/secret 边界；状态页只在
  真实 gate 全部通过后声明 P1 完成；
- 重点测试：[AC-12][AC-13][AC-14][AC-15] 全量回归、Schema、链接、站点、build/wheel/隔离 CLI、Fake 5/5、
  真实正常任务 4/4 + canary、反向架构/安全审查；
- 验证命令：本 Plan 最终离线命令与受限真实 gate 均已运行；
- 回退方式：任何 gate 失败都保持 Feature/Plan active、P1 进行中；不覆盖失败证据，不删除用户数据。

## 耦合评估

- 新增/修改公共接口：config v1、RunProfile v2、ProviderSelection、RunCreated v3、CLI `--config`
  和 live report v1；既有 `ModelProvider.stream` 不变；
- 依赖模块：interfaces 依赖 bootstrap/application；bootstrap 可导入配置和具体 adapter；application/runtime/
  domain 只依赖 BearAgent 类型与 ports；
- 新依赖：仅 Anthropic 官方 SDK；版本由 `pyproject.toml` 声明并由 `uv` 更新 lockfile；
- 依赖方向：OpenAI/Anthropic SDK 类型不得进入 domain、ports、runtime、application、Event、CLI contract；
- 循环风险：catalog loader 不依赖 bootstrap；factory 不被 adapter/core 回调；report/rubric 不进入 AgentLoop；
- 扇出控制：配置解析、SecretStr 解封、protocol factory、各 wire translator、preflight、rubric、report
  分开，避免 `bootstrap.py` 或 live runner 成为上帝模块。

## 关键注释原则

只给不直观的安全/恢复决定写注释：

- 为什么 catalog 的直接 `api_key` 必须使用 `SecretStr`、被 Git 忽略且永不进入 Event/日志/report；
- 为什么 protocol 必须显式选择且禁止 fallback，避免 key/Prompt 错发和一次 Activity 隐式多次调用；
- 为什么 Event 只保存 Provider selection，不保存 endpoint/env/key；
- 为什么 unknown/缺 usage/ToolCall 不一致必须协议失败，不能猜测；
- 为什么 live preflight 必须在 DB、workspace 和 SDK client 之前完成；
- 为什么模型返回多个 ToolCall 后仍由 AgentLoop 逐个重新检查预算和 Policy。

直接字段翻译、Pydantic 构造、Enum 分支和测试 fixture 不加逐行解释式注释。

## 每一步都要检查

- [x] Event v1/v2 永久可读，新 Run 只写明确 v3；SQLite 无隐式 migration；
- [x] Provider selection 只保存有限身份，endpoint、key、header、SDK/raw response 不持久化；
- [x] 每个 adapter 运行同一 contract，禁用 SDK 自动重试，timeout/cancel/resource limits 明确；
- [x] 未知 protocol/event、缺 usage 和 ToolCall 不一致明确失败，不探测或 fallback；
- [x] 所有 workspace 动作仍经过 Registry、prepare、FixedToolPolicy、ToolExecutor 和 WorkspaceBoundary；
- [x] 多 ToolCall 串行执行，预算与 Policy 每次重新检查；
- [x] live preflight 未通过时数据库、workspace、SDK client 和 Provider 调用均为零；
- [x] live runner 只读取公开 fixture，并受显式 opt-in、非零预算和 suite cost cap 约束；
- [x] domain/runtime/application 无 Provider SDK、Typer、SQLite 或具体 adapter 类型泄漏；
- [x] AC 编号与 Plan 步骤、测试和文档回链；
- [x] 工程文档、site beginner、site developer、current status 和 P1 milestone 同步。

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
uv run python scripts/generate_runtime_configuration_schemas.py
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
uv build
uv run --isolated --no-project --with .\dist\bearagent-0.1.0-py3-none-any.whl bearagent doctor --json
uv run --directory .\dist --isolated --no-project --with .\bearagent-0.1.0-py3-none-any.whl python ..\scripts\smoke_wheel_cli.py
git diff --check
```

2026-08-23 最终离线结果：`uv lock --check`、Ruff、format、Pyright 通过；pytest 445/445；三个 schema
生成器无未解释漂移；Markdown 本地链接通过；Starlight 构建 35 页；sdist/wheel 构建和两个隔离 wheel
smoke 通过。安全复核确认默认 pytest/CI/build/doctor 不读取真实 Provider key、不发出模型请求；Fake P1
任务保持 5/5，三个 production adapter 的 contract/mock transport 全部通过。

最终 suite v1.1.1 attempt
`20260823T094157Z-04218aee-31a4-42e4-aaf0-ed78b97c9b70` 使用 production composition、五个独立
workspace/SQLite 和重开查询通过 5/5。总 usage 为 13,640 input、1,415 output tokens；按确认快照记录
2,324 microUSD。四个普通任务成功并生成匹配 Artifact；安全任务产生预期 `budget_exhausted`，越界
读取失败且 canary 未持久化。脱敏报告见
[F-0017 P1 live report v1](../evidence/F-0017-p1-live-report-v1.json)。

前两个失败 attempt 保留在本机 `data/live-evals/p1/`，没有被覆盖：第一个暴露 Chat wire-name 与
thinking 兼容问题；第二个证明协议修复后五个 Run 均完成，并暴露 pricing 未注入和搜索 expected call
过度约束。两处 gate 问题均先补回归测试，再创建新的独立 attempt。
