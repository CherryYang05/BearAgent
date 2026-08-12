---
title: "ADR-0010: OpenAI Responses as the first model service adapter"
status: accepted
date: 2026-08-13
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0010：首个模型服务适配器使用 OpenAI Responses API

## Context

F-0004 必须把第一个真实模型接到 BearAgent 的统一内部模型接口。此选择会新增生产依赖，确定
流式响应、工具调用和错误的首个翻译边界，并影响后续运行时的超时、用量统计与重试规则，因此
属于 S2 决策。

OpenAI 官方文档把 Responses API 用于当前的推理、工具调用和多轮工作流，并通过 HTTP
服务器推送事件提供带类型的流式过程事件。BearAgent 只采用其中可移植的文本、函数调用、用量、
完成信号与安全错误，不采用服务商托管工具、服务商会话状态或服务商侧的 Agent 编排。

## Decision drivers

- 可维护性：首个适配器应小且直接，不能让聚合框架的类型主导内部数据模型。
- 恢复规则：适配器不暗中重试；后续运行时需要为每次尝试留下事实记录。
- 安全：外部输出不可信，API key 与原始错误/响应不得进入领域错误或 Event。
- 复杂度/交付时间：先支持一种生产协议，并用替代实现和注入式客户端做确定性测试。
- 兼容与迁移：BearAgent 内部接口必须能由未来第二个适配器实现，不能暴露 SDK 的联合类型。

## Considered options

### Option A: 官方 OpenAI Python SDK + Responses streaming

优点：协议与 typed SDK 同源；支持文本、函数调用、usage 和 request identity；不用维护 HTTP/SSE
解析器。缺点：增加 SDK 生产依赖，流式事件演进仍需适配器共用接口测试隔离。

### Option B: 手写 HTTP/SSE client

优点：依赖更少，可完全控制传输格式。缺点：需要自行维护认证、连接池、SSE 解析、超时
和 API 演进；对第一个适配器不划算且更容易泄漏原始响应。

### Option C: 多模型服务商聚合框架或 OpenAI-compatible Chat Completions

优点：供应商覆盖更广。缺点：抽象会提前受最低公分母与框架类型约束；“compatible”实现的
流式响应、工具调用和错误细节并不一致；当前没有多服务商需求证据。

## Decision

- 首个生产适配器使用官方 OpenAI Python SDK 的异步 Responses 流式 API。
- SDK 只允许出现在 `src/bearagent/adapters/model/`；内部接口与数据模型只暴露 BearAgent 的
  Pydantic 类型。
- 适配器只翻译明确允许的事件，组装完整函数调用，并在唯一的模型完成事件中统一用量和元数据；
  遇到未知关键过程、缺少或重复完成事件、格式错误的输出时安全失败。
- API key、base URL 与客户端配置在程序组装边界注入，不属于 `ModelRequest`。
- 每次请求都有明确超时；适配器不自动重试，异常只转换为稳定且安全的错误类别。
- `CancelledError` 原样传播；流式响应中途失败时不产生模型完成事件。
- F-0004 不使用服务商托管工具、服务商保存的会话、后台模式、WebSocket 或
  `previous_response_id`。BearAgent 的 Event 日志仍是事实来源。

官方依据：

- [OpenAI Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses)
- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI API error codes](https://developers.openai.com/api/docs/guides/error-codes)

## Consequences

### Positive

- 运行时获得稳定、不依赖特定模型服务商且可测试的真实模型边界。
- SDK/协议升级集中在单个适配器；后续第二个适配器可通过同一套共用接口测试验证这个内部接口。
- 重试、预算和持久化仍由 BearAgent 运行时控制，不被 SDK 的隐式行为遮蔽。

### Negative / debt accepted

- 增加 OpenAI SDK 与传递依赖，需要 lockfile、依赖扫描和升级验证。
- 第一版只覆盖 BearAgent 需要的 Responses 事件子集；新增多模态或托管工具必须另行扩展 Feature Spec。
- 默认 CI 不能证明真实账号、模型可用性或网络行为；只证明适配器的翻译规则。

## Migration and rollback

当前没有生产环境的 `ModelProvider` 或持久化模型请求，因此无需迁移数据。回退时可删除 SDK
依赖、适配器和新增的数据格式，并恢复 P0 的替代实现。若后续已持久化这些数据格式，则通过新版本与
事件升级转换迁移，不能改写历史 Event。

## Validation

- 内部数据格式的 JSON Schema 快照，以及深层不可变性和边界测试。
- 注入式异步模拟流覆盖文本、函数调用、用量、模型完成事件和格式错误事件。
- 错误分类、取消传播、不自动重试和敏感信息清除测试。
- 架构导入测试与安装包检查，证明 SDK 没有越过适配器边界。
- 在用户显式提供 API key 时可运行独立冒烟测试；默认 CI 不调用外网。
