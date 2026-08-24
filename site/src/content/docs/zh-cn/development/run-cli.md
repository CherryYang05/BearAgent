---
title: F-0005 生产 CLI 和查询服务实现导读
description: 找到 Run profile、composition root、EventStore query、CLI JSON 契约和边界测试。
bearStatus: implemented
sourceRefs:
  - F-0005
  - PLAN-F-0005
  - ADR-0014
  - F-0017
  - ADR-0015
---

修改 `bearagent run` 时，先沿着 `interfaces -> bootstrap/application -> ports -> adapters` 阅读。CLI 只
负责解析和渲染；业务事实仍来自 AgentLoop、Reducer 和 EventStore。

## 代码地图

| 位置 | 责任 |
|---|---|
| `domain/agent.py` | 严格、非敏感的 RunProfile v1/v2 |
| `configuration.py` | config v1 的 Provider 列表、HTTPS/base URL、直接 key、SecretStr、无 pricing 和条目上限 |
| `domain/providers.py` | `ModelProtocol` 与非敏感 `ProviderSelection` |
| `domain/queries.py` | RunInspection、Provider 选择与有界 EventPage |
| `application/run_queries.py` | 只通过 EventStore 查询 projection、Event 和 Artifact |
| `bootstrap.py` | 读取 profile/catalog，按显式 protocol 组装 adapter、SQLite、Tools、Policy 与 AgentLoop |
| `interfaces/cli/contracts.py` | version 1 Run/inspect/events result 与 safe error envelope |
| `interfaces/cli/renderers.py` | human 摘要和单对象 JSON 序列化 |
| `interfaces/cli/main.py` | Typer 参数、退出码和异步 application 调用 |

## composition root 只做组装

`build_run_services` 先校验 profile、catalog 和 workspace。RunProfile v2 的 `provider_id` 必须精确
命中一个 catalog 条目；factory 只按条目的 `ModelProtocol` 创建 Responses、Chat Completions 或
Anthropic Messages adapter。它不根据厂商、URL 或 model 猜协议，也不 fallback。

随后 composition 选择 profile 明确列出的 Tool。未配置的 Tool 不进入 Registry，因此既不会出现在
ModelRequest 中，也不会被 Policy 允许。同一个 SQLite Store 同时交给 AgentLoop 和 RunQueryService。

测试可以注入 Provider-neutral Fake Provider；真实 CLI 不暴露 `--api-key`，只从选中条目指定的环境
变量读取 key。SDK client 延迟到首个模型 Activity；零预算不创建 client，缺 key 时首个 Activity/Run
保存安全的 `provider_authentication`。domain、runtime 和 application 不导入 OpenAI/Anthropic、
SQLite adapter 或 Typer；architecture test 持续检查这个方向。

Profile 与 catalog loader 都使用文件描述符读取最多 128 KiB，并比较打开前后快照。链接、reparse
point、替换竞态、非法 UTF-8、未知字段、非法 URL/key 和未知字段都会变成有限的 safe Error。
`inspect/events` 在初始化前要求数据库已存在且是普通文件，避免一次拼错路径悄悄创建空库。

## query service 为什么不写 SQL

`RunQueryService.inspect` 先取得 RunState，再以最多 1,000 条一页扫描 Event，总量最多 10,000 条。
每页必须属于同一个 Run，sequence 连续并且不超过 projection 的 `last_sequence`。RunCreated v3
经过正式 parser 后提供安全 Provider 选择；v2 ToolCallCompleted payload 才允许提取
`workspace.write` Artifact。

`events` 同样先读取 projection，之后只查询当时已提交的有限前缀。返回的 EventPage 验证 Run ID、
顺序、游标、页大小和 `has_more`。查询层没有 SQL、SQLite row 或第二个 Reducer。

## `run OBJECTIVE` 为什么还能有子命令

Typer 通常要求 command group 后先写子命令，但路线图已经固定 `bearagent run OBJECTIVE`。F-0005 的
`DefaultRunGroup` 只做一条解析规则：第一个 token 不是 `inspect/events` 时，路由到隐藏的 execute
handler。`run --help` 保留组帮助；目标若恰好叫 `inspect`、`events` 或以短横线开头，可使用
`bearagent run -- OBJECTIVE`。integration test 同时覆盖无子命令执行和两个查询子命令，防止语法回归。

## 输出和失败边界

human 与 JSON renderer 读取同一个 Pydantic result。Run 成功退出 0；Run 以 failed 终止或安全边界
失败退出 1；Typer 用法错误退出 2。JSON stdout 只有一个 versioned object，预分配 Run ID 只写 stderr。
默认 Event 摘要不打印 payload；完整 payload 只在显式 `events --json` 中出现。

不要把 `except Exception` 的原始文本直接交给用户。已规范化的 BearAgentError 可以保留 ErrorInfo；
未知异常只能变成 `internal_error`。取消不在这一层改写为 terminal Event。

## Fake Provider 怎样验证真实接线

`tests/evals/test_p1_agent_loop_tasks.py` 定义五个版本化文件任务。每个任务的 Fake Provider 是逐请求
脚本：第 1 次模型请求返回哪一个 Tool call、第 2 次返回什么结果都事先固定；它不会读取 Prompt 后临时
编造答案。测试断言请求次数、Tool 名称和参数、Event sequence、终止原因、输出内容与 Artifact hash。

production composition 测试只通过 `build_run_services(model_provider=fake)` 替换 ModelProvider。SQLite、
WorkspaceBoundary、四个真实 Tool、Registry、FixedToolPolicy、ToolExecutor、AgentLoop 和 query service
仍使用生产实现。任务完成后重新打开 SQLite，再通过 `inspect/events` 检查已提交事实。

`tests/integration/test_run_cli.py` 在 Typer 边界 monkeypatch 同一个 composition seam，然后真实调用
`run/inspect/events`。它也不注入 Provider 地验证 v1/v2 生产失败：零预算不创建 SDK client；缺少
缺失或非法 key 会在数据库创建前返回 `invalid_input`；Event/CLI 不泄露 endpoint 或 key。
`tests/security/test_model_provider.py` 则把敏感文本放进
client 初始化异常，确认公开 Error 不复制原始内容。

## 从哪里看证据

- `tests/unit/test_run_queries.py`：分页、游标、缺失 Run、总量上限和不完整历史；
- `tests/unit/test_provider_config.py`、`tests/unit/test_run_profile_versions.py`：catalog/profile 边界；
- `tests/unit/test_provider_composition.py`：三种 protocol 的唯一 production selector；
- `tests/integration/test_run_cli.py`：v1/v2、Fake Provider + production composition + SQLite 的 CLI 全链；
- `tests/security/test_cli_boundaries.py`：profile secret、损坏 Event 和未来 migration 脱敏；
- `tests/recovery/test_agent_loop_boundaries.py`：取消与写后 append 失败的查询结果；
- `tests/evals/test_p1_agent_loop_tasks.py`：五个固定任务通过 production composition 并重开查询；
- `tests/contract/test_cli_schemas.py`：machine-readable 输出 Schema 快照。

F-0017 没有增加 SQLite migration、网络 Tool、恢复或 Approval。live runner 仍默认关闭；DeepSeek V4
suite v1.1.1 已通过真实 5/5 并生成脱敏报告。
