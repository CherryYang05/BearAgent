---
title: BearAgent 是什么
description: BearAgent 的目标、边界和当前成熟度。
bearStatus: mixed
sourceRefs:
  - architecture/overview
  - roadmap
---

BearAgent 是一个轻量、local-first、可自托管的个人 Agent Runtime。它希望安全、可靠地执行
需要多次模型与工具交互的本地任务。

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

BearAgent 的重点是围绕模型建立一个可以约束、记录、恢复和验证执行过程的 Runtime。

## 第一阶段有意保持很小

项目首先限制为单用户、单进程、SQLite 和 CLI-first。P1 的目标只是让本地 CLI 完成一次真实、
受限、可追踪的文件任务。Web UI、MCP、Memory、多 Agent 和浏览器控制都不会抢在运行时基础之前。

## 当前能做什么

目前已实现 Provider 无关的 ID、Message、Error 和 Event envelope；真实模型、Agent Loop、工具和
SQLite 仍属于后续 P1 Feature。因此现在最适合做的是阅读领域契约和参与构建，而不是把它当作
已经可用的个人助理。
