---
title: 为什么做 BearAgent
description: BearAgent 先服务谁、先完成什么，以及为什么不追求功能数量。
bearStatus: mixed
sourceRefs:
  - product-positioning
  - roadmap
  - F-0017
---

BearAgent 想让个人 Agent 在本地可靠地完成长任务：用户能看清每一步，系统不会在结果不明时乱
重试，危险操作也不能只因为模型提出了请求就被执行。

:::caution[这是产品方向，不是当前功能清单]
当前已完成工程基础、内部数据类型、状态与预算规则、SQLite EventStore、三种模型协议 adapter、统一
ToolExecutor、workspace 读写 Tool、原子输出 Artifact、有界 Agent Loop、本地文档站和
`run/inspect/events` production composition。F-0017 的真实模型 gate 已通过 5/5，P1 已关闭；P2/P3
仍是规划，不是当前功能。
:::

## 第一个用户和第一个任务

BearAgent 首先服务愿意在自己电脑或服务器运行 Agent 的开发者、研究者和高级用户。第一个任务
不是“做一个全能助理”，而是：在指定工作区中阅读仓库和本地文档，比较资料，并把结果写到
`outputs/**`。

同一组任务会贯穿前三个阶段：

- P1 证明任务能完成，而且模型调用、工具操作、预算和错误可以查看；
- P2 人为中断进程，证明每次复用、重试、reconcile 或 `UNKNOWN` 都有已保存事实支撑；
- P3 尝试越权、篡改批准参数和读取宿主 secret，证明授权与隔离两道门真正生效。

## BearAgent 选择负责哪一层

成熟 Agent 产品通常同时优化界面、模型、工具、工作区和生态；Agent 框架则帮助开发者快速组织
流程。BearAgent 不靠“别人没有持久化或沙箱”来证明差异，也不计划复刻 Manus 或 Claude Code。

它选择一个更窄的责任：在个人能够维护的本地系统里，用同一份执行记录回答三个问题——任务
做过什么、为什么继续或停下、某个外部动作为什么被允许。

## 为什么先不做 Web、MCP 和多个 Agent

这些功能会扩大入口和能力，却不会自动解决重复写入、权限判断和故障恢复。如果核心执行记录还
不可靠，增加更多工具只会增加无法解释的失败方式。

因此 P1 至 P3 保持单用户、单 Agent、单个 Runtime 进程、SQLite 和 CLI。P4 才加入 HTTP、认证和
安全自托管，再依次接入 Skill、MCP、Web 和 Memory，并要求它们继续经过原有的 Event、恢复、Policy
和 runner 路径。

完整阶段顺序见[阶段路线](/BearAgent/zh-cn/project/milestones/)，当前事实见
[实现状态](/BearAgent/zh-cn/project/status/)。
