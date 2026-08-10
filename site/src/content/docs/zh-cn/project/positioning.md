---
title: 产品定位
description: BearAgent 为谁解决什么问题、与其他 Agent 的差异以及如何证明差异化。
bearStatus: mixed
sourceRefs:
  - product-positioning
  - roadmap
---

BearAgent 是一个**可检查、可恢复、权限外置的 local-first Agent Runtime**，面向希望把长期文件与开发任务交给 AI、又不愿把权限和执行历史交给黑箱的个人开发者与高级用户。

:::caution[内容状态：已接受定位 + 分阶段目标]
定位描述 BearAgent 要成为的产品。当前只完成工程基线、领域契约和本地文档站，尚不能执行真实 Agent 任务；请同时查看[当前实现状态](status.md)。
:::

## BearAgent 负责回答三个问题

1. **发生了什么？** 模型与 Tool Activity、预算、错误和 Artifact 都有结构化事实。
2. **这件事允许发生吗？** 权限来自 Runtime Grant 与 Policy，不来自 Prompt、模型或 Tool 输出。
3. **失败后从哪里继续？** 只从持久安全边界恢复；不能确认的副作用进入 `UNKNOWN`。

## 它不是什么

- 不是以模型、Tool、渠道和角色数量取胜的“万能 Agent”；
- 不是 Manus、Claude Code 或其他产品的开源复刻；
- 虽然首个任务域包含仓库文件，但不把长期定位限制为 Coding Agent；
- P1-P3 不是通用 Agent framework、企业多租户平台或无代码 Workflow builder。

BearAgent 选择的是一个更窄的产品楔子：**最小但可信的个人 Agent 执行底座**。

## 差异化怎样被证明

| 阶段 | 用户价值 | 可复现证据 |
|---|---|---|
| P1 Inspectable Execution | 一个真实本地 Run 有界、受限、过程可查 | CLI 文件任务；路径拒绝；预算终止；Activity/Event/Artifact 视图 |
| P2 Safe Recovery | 崩溃后从安全边界继续，不重复已确认副作用 | kill-point、Checkpoint 重建、幂等、receipt 与 `UNKNOWN` 演练 |
| P3 Governed Self-hosting | 模型只能在授权与隔离边界内行动 | Approval 篡改阻断、runner secret/host 隔离、备份恢复与 HTTPS |

在对应证据完成前，公开文档只能说“设计为”或“规划中”，不能把目标写成当前能力。

## 为什么还值得自己写 Agent

基础模型循环已经很容易搭建，差异却越来越集中在循环之外：任务域、上下文与数据所有权、工具执行环境、权限、崩溃恢复、产品入口和评测标准。不同 Agent 选择了不同责任边界，才会产生大量看起来相似、实质不同的项目。

BearAgent 不把“自己实现循环”当作价值；它选择对**执行事实、运行时权限和失败恢复**负责，并用故障与安全测试持续证明这条边界。

工程层面的完整定位、参考项目比较和对外措辞见仓库中的[产品定位](https://github.com/CherryYang05/BearAgent/blob/main/docs/project/product-positioning.md)，详细交付顺序见[阶段与里程碑](milestones.md)。
