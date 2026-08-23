---
title: 先看 BearAgent 怎样分工
description: 从一次本地文件任务理解 Runtime、domain、port、adapter、EventStore 和用户入口各自负责什么。
bearStatus: mixed
sourceRefs:
  - architecture/overview
  - F-0001
  - F-0002
  - F-0003
  - F-0004
  - F-0006
  - F-0007
  - F-0008
---

BearAgent 的架构不是从“需要多少服务”开始，而是从一次任务的责任开始：谁理解目标，谁能接触外部
环境，谁决定权限，谁保存事实，进程中断后又能依据什么继续。

假设用户要求：读取 `docs/` 下几份文件，把结论写入 `outputs/report.md`。理想的完整路径是：

```mermaid
flowchart TB
    U["用户 / CLI"] --> APP["Application\n启动或查询一个 Run"]
    APP --> RT["Runtime\n推进状态、预算和 Agent Loop"]
    RT --> MP["Model port"]
    RT --> TE["ToolExecutor + Policy"]
    RT --> ES["EventStore port"]
    MP --> MA["模型 adapter"]
    TE --> FT["受限文件 Tool"]
    ES --> SA["SQLite adapter"]
```

:::caution[完整路径尚未全部接通]
当前已实现内部数据、Run/Activity 状态、Reducer、预算、SQLite EventStore、OpenAI Responses adapter，
以及 Registry、固定 Policy、ToolExecutor 和四个 workspace Tool。ContextBuilder、Agent Loop 和 Run
CLI 尚未实现；恢复、用户 Approval 和 sandbox 属于后续阶段。
:::

## 六个区域分别回答什么问题

| 区域 | 它回答的问题 | 当前代码位置 |
|---|---|---|
| Domain | 模块之间允许交换什么数据？ | `src/bearagent/domain/` |
| Runtime | 下一步能不能发生，状态怎样变化？ | `src/bearagent/runtime/` |
| Port | 核心需要外部系统提供什么行为？ | `src/bearagent/ports/` |
| Adapter | SQLite、OpenAI 或具体 Tool 怎样满足行为？ | `src/bearagent/adapters/` |
| Application | 一个用户用例怎样编排这些能力？ | `src/bearagent/application/`，尚待建设 |
| Interface | CLI 或未来 API 怎样接收和展示请求？ | `src/bearagent/interfaces/` |

这套划分不是为了让目录显得“企业级”。它的实际效果是：Reducer 不需要知道 Event 存在 SQLite，
Tool Policy 不需要知道请求来自 CLI 还是 Web，模型 adapter 也不能把 SDK response 类型带进 Runtime。

## Port 和 adapter 的区别

`port` 是核心代码提出的内部接口。例如 `ModelProvider` 只要求：给它一个 `ModelRequest`，返回一条
`ModelEvent` 异步流。它不提 OpenAI 的 SSE class。

`adapter` 是一种具体翻译实现。OpenAI adapter 把 BearAgent request 翻成 Responses API 参数，再把
SDK event 翻回 BearAgent event；Fake adapter 则回放测试预设事件。

EventStore 也相同：内存 adapter 和 SQLite adapter 内部做法完全不同，但同一组 contract test 要求
它们对追加、冲突和读取顺序给出一致结果。

## 三条边界比“用了什么框架”更重要

### 数据边界：外部对象先翻译

Model、Tool、数据库和用户输入都先进入 BearAgent domain model。未知字段、非法 JSON、重复 ID、
不匹配的消息 role 和超大输入在这里被拒绝。核心不接收某个 SDK 的便利对象。

### 权力边界：Model 只能请求，不能授权

Model output、文件内容和 Tool result 都是不受信任数据。ToolRequest 必须经过精确 Registry、参数
准备、Policy 和统一 Executor。Prompt 或 Tool schema 不能授予运行权限。

先沿[一次请求怎样穿过 BearAgent](runtime-flow.md)看完整顺序，再用
[P1 为什么这样设计](p1-decisions.md)理解单进程、Event、默认拒绝 Policy、相对路径、原子输出和
串行 Loop 的取舍。准备修改实现时，从[开发者入口](../development/)进入代码。
