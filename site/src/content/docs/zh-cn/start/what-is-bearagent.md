---
title: BearAgent 是什么
description: BearAgent 的目标、边界和当前成熟度。
bearStatus: mixed
sourceRefs:
  - architecture/overview
  - roadmap
---

BearAgent 是一个可检查、可恢复、权限外置的 local-first Agent Runtime。它面向希望把长期文件
与开发任务交给 AI、又不愿把权限和执行历史交给黑箱的个人开发者与高级用户。

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

这让 BearAgent 更像一个个人 Agent 执行底座，而不是聊天 UI、垂直应用或另一个功能齐全的
Coding Agent。完整说明见[产品定位](../project/positioning.md)。

## 第一阶段有意保持很小

项目首先限制为单用户、单 Agent、单进程、SQLite 和 CLI-first。P1 证明可检查执行，P2 证明
安全恢复，P3 证明权限治理与隔离自托管。Web UI、MCP、Memory、多 Agent 和浏览器控制都不会
抢在这三个闭环之前。

## 当前能做什么

目前已实现不依赖特定模型服务商的 ID、Message、Error、Event 通用外壳、SQLite EventStore 与真实模型
适配器；Agent Loop 和工具仍属于后续 P1 Feature。因此现在最适合做的是阅读内部数据规则和参与构建，而不是把它当作
已经可用的个人助理。
