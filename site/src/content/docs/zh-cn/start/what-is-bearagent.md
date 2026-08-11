---
title: BearAgent 是什么
description: BearAgent 的目标、边界和当前成熟度。
bearStatus: mixed
sourceRefs:
  - architecture/overview
  - roadmap
---

BearAgent 是一个面向本地长任务、失败语义诚实的 local-first Agent Runtime。它把模型与工具
动作记录为持久事实，由模型外的确定性 Policy 强制授权；崩溃后只在结果可确认时继续，无法确认
的外部副作用停在 `UNKNOWN` 等待 reconcile。

:::note[内容状态：设计目标]
这一定义描述项目已经接受的方向，不表示所有能力现在都已实现。请同时查看[当前实现状态](../project/status.md)。
:::

## 为什么不是再做一个聊天界面

一次模型调用很容易演示，但真正把任务交给 Agent 后，会出现更难的系统问题：

- 模型可能无限循环、超出预算或返回不合法的工具参数；
- 工具可能超时，外部写操作可能发生了却没有留下成功记录；
- 进程可能在任务中途退出；
- 模型看到的文本不能等同于系统权限；
- 最终答案看似正确，执行过程仍可能违反规则。

BearAgent 的重点是围绕模型建立一个可以约束、记录、恢复和验证执行过程的 Runtime：

- 发生了什么：Run、Activity、Event、预算和 Artifact 可以检查；
- 允许做什么：权限来自模型之外的 Grant、Policy 与 Approval；
- 从哪里继续：只从持久安全边界恢复，不确定副作用进入 `UNKNOWN`。

这不表示其他 Agent 都没有日志、恢复、审批或 sandbox；区别假设在于 BearAgent 是否能用统一
Activity/Attempt/Event/Receipt 契约和故障注入，更严格地证明副作用结果。完整说明见
[产品定位](../project/positioning.md)。

Runtime 本身不回答“用户能完成什么”。因此 P1 同时交付 Repo/Document Research Agent 作为首个
参考应用，用同一组真实任务贯穿 P1 的执行检查、P2 的崩溃恢复和 P3 的授权/隔离。

## 第一阶段有意保持很小

项目首先限制为单用户、单 Agent、单进程、SQLite 和 CLI-first。P1 证明可检查执行，P2 证明
安全恢复，P3 证明权限治理与隔离自托管。Web UI、MCP、Memory、多 Agent 和浏览器控制都不会
抢在这三个闭环之前。

## 当前能做什么

目前已实现 Provider 无关的 ID、Message、Error 和 Event envelope；真实模型、Agent Loop、工具和
SQLite 仍属于后续 P1 Feature。因此现在最适合做的是阅读领域契约和参与构建，而不是把它当作
已经可用的个人助理。
