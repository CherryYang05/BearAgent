---
title: 从命令行运行并检查一次 Run
description: 用同一个 SQLite 数据库启动文件任务、查看状态，再分页读取已经提交的 Event。
bearStatus: implemented
sourceRefs:
  - F-0005
  - ADR-0014
  - F-0016
  - F-0017
  - ADR-0015
---

你运行一个文件任务后，最先要回答的不是“模型说了什么”，而是三个更具体的问题：这次 Run 的 ID
是什么、最终状态是什么、哪些事实真的保存下来了。F-0005 用三个命令回答它们：

```powershell
bearagent run "阅读 docs 并把总结写到 outputs/summary.md"
bearagent run inspect <run-id>
bearagent run events <run-id> --after-sequence 0 --limit 100
```

本页解释三条命令为什么读取同一批事实。安装、profile 全字段、Provider 环境、所有选项、退出码和
排错步骤见[P1 命令行完整使用手册](../guides/cli.md)。

## 一次命令怎样接到已有边界

```mermaid
flowchart TB
    C["CLI 校验 objective 和路径"] --> B["bootstrap 读取 Run profile 和 BearAgent config"]
    B --> G["按显式 protocol 组装一个 Provider、SQLite、Policy 和 workspace Tools"]
    G --> L["AgentLoop 保存并执行 Run"]
    L --> R["RunResult"]
    R --> H["human 或 JSON 输出"]
    D["inspect / events"] --> Q["application query service"]
    Q --> S["EventStore port"]
```

CLI 不计算状态，也不读取 SQLite 表。`run` 把经过校验的 `RunInput` 交给 AgentLoop；`inspect` 和
`events` 把 Run ID 交给 application query service。query service 再通过 EventStore port 读取同一份
projection 和 Event，所以不存在“终端显示成功、数据库却是另一种状态”的第二套规则。

## Run profile 为什么不放密钥

默认配置分成两份。`data/config.json` 描述服务怎样连接和默认使用哪个模型：
`provider_id`、厂商显示名、protocol、HTTPS base URL、直接填写的 `api_key`、模型列表和
`default_model`。该文件被 Git 忽略且必须按敏感文件保护。RunProfile v2
`data/p1-run-profile.json` 只通过 `provider_id` 选择服务，再保存 Agent 指令、Tool 白名单和预算。
Key 和 model 不在 RunProfile 中重复配置；config 明确拒绝 pricing，普通 Run 使用 `unpriced`。

两种配置都是有限大小的普通 UTF-8 JSON 文件。未知字段、链接、非法编码、引用不存在和越界值会在
创建数据库和 Run 前失败。RunProfile v1 仍可读，并映射到 legacy Responses 配置；新配置使用 v2。

profile 不是“每个 Tool 一份 JSON”，也不需要为每个问题重新生成。每个 Tool 的参数 schema 已由
`ToolSpec` 定义；profile 只选择这个 Agent 能看到哪些 Tool。同一 config/profile 可以先后运行
“总结 docs”和“比较两份说明”，每次变化的是 objective。只有服务/model、Agent 指令、预算或 Tool
权限发生变化时才需要修改配置。

仓库提供的 v1/v2 示例 profile 都把预算设为 0。使用它启动 Run 时，AgentLoop 会保存 RunCreated、
RunStarted 和 `budget_exhausted` RunFailed；SDK client 不会创建，模型和 Tool 都不会调用。预算非零
但所选 key 缺失时，首个模型 Activity 和 Run 会以安全的 `provider_authentication` 失败。这两种情况
都能用 `inspect/events` 查看。

## inspect 与 events 看的是不同层次

`inspect` 返回 Reducer 已计算出的完整 RunState，包括预算、usage、Activity、terminal Error 和最后
sequence。新 Run 还显示 RunCreated v3 保存的 `provider_id`、config version、protocol、配置 model 和
pricing version（普通 Run 为 `unpriced`），不显示 base URL 或 key。它也会分页扫描已提交的 v2 Tool completed Event，从
`workspace.write` 结果重建 Artifact 元数据。如果 Event 总量超过可信上限，命令会明确失败，不会把不完整 Artifact 列表说成完整结果。

`events` 返回一页不可变事实，并带回 `next_after_sequence` 和 `has_more`。默认 human 输出每条只显示
sequence、时间、类型和 schema version，不显示 payload。`--json` 是显式完整导出，可能包含用户目标、
模型文本和 ToolResult，不应当作普通日志公开。

## 中断后会看到什么

如果调用被取消，已经提交的 Event 仍在数据库里。`inspect` 会如实显示 `running` 以及最后一个
PENDING/RUNNING Activity；它不会猜测成功，也不会自动追加 RunFailed。若文件已经写成，但
ToolCallCompleted 没有提交，查询也不会从文件系统反推一个 Artifact。

自动恢复、retry、Attempt、Receipt 和 `UNKNOWN` 属于 P2。F-0005 的自动验收使用注入式 Fake Provider，
没有读取真实 key 或调用真实模型。真实模型 API gate 与完整 P1 Reality Check 仍待完成。

继续阅读[生产 CLI 和查询服务实现导读](../development/run-cli.md)，查看代码位置、Schema 和故障测试。
