---
title: 跟一次 SSE 读懂模型 adapter
description: 从 ModelRequest 到 ModelCompleted，理解 OpenAI Responses 事件怎样在边界翻译、关联、限流并安全失败。
bearStatus: implemented
sourceRefs:
  - F-0004
  - OpenAI Responses API
---

模型 adapter 的工作不是把 SDK response 原样交给 Runtime。它要把一次外部流转换成 BearAgent 认识的
有限事件，同时拒绝不完整、矛盾或超出当前支持范围的响应。

```text
ModelRequest
    ↓ 翻译 input、tools、timeout
OpenAI Responses SSE
    ↓ 逐项校验和累计大小
ModelTextDelta / ModelToolCall
    ↓ 恰好一个成功终点
ModelCompleted
```

从 `domain/model.py` 读到 `ports/model.py`，最后进入
`adapters/model/openai_responses.py`，会比一开始就在 490 行 adapter 中找入口更清楚。

## 内部模型数据只表达 Runtime 需要的内容

`ModelRequest` 包含：模型名、消息历史、可用 Tool 定义、最大输出 token、timeout 和 prompt version。
它不包含 OpenAI SDK 类型。

构造请求时会检查：

- 消息数、Tool 数、描述长度、总输入字符和 timeout 有上限；
- Tool 名称唯一，input schema 根节点必须是 JSON object；
- 历史中的 `tool_call_id` 和 `provider_call_id` 都不能重复；
- Tool result 必须引用前面出现且尚未回答的 Tool call；
- Tool schema 只是告诉模型“可以怎样提请求”，它本身不授予执行权限。

最后一条尤其重要。模型看到了某个 Tool，不代表 Runtime 一定允许这次具体参数；真正执行时仍要经过
Tool Registry、参数准备和 Policy。

## Port 只承诺一条异步事件流

`ModelProvider.stream(request)` 返回 `AsyncIterator[ModelEvent]`。Runtime 只需要认识三种成功事件：

| 事件 | 含义 |
|---|---|
| `ModelTextDelta` | 一个非空文本片段 |
| `ModelToolCall` | 一个完整、已解析为 JSON object 的函数调用 |
| `ModelCompleted` | 唯一成功终点，包含 Provider request ID、模型、停止原因和可选 usage |

“usage 缺失”和“usage 为 0”是两种不同情况，所以 `ModelCompleted.usage` 可以是 `None`。Adapter 不会
为了填满字段而猜 token。

## 请求怎样翻译成 Responses API

`OpenAIResponsesProvider.stream` 调用 `responses.create` 时固定：

- `stream=True`，逐项处理 SSE；
- `store=False`，不要求 Provider 保存响应；
- `parallel_tool_calls=False`，与当前串行 Activity 规则一致；
- 每次请求使用 `ModelRequest.timeout_ms`；
- OpenAI client 必须 `max_retries=0`。

禁用 SDK 自动重试不是说系统永远不重试，而是防止 adapter 在 Runtime 不知情时重复请求。未来由
Runtime 根据 Event 和失败语义决定是否建立新尝试。

`_translate_input` 会把 BearAgent Message 展开为 Responses input item。Assistant 的 Tool call 使用
`provider_call_id`，之后 Tool result 通过内部 `tool_call_id` 找回它。历史缺少关联 ID 时，adapter
直接报告协议错误。

## 流式事件怎样变成三个内部事件

`_translate_event` 对每个 SDK event 做显式分派：

- 非空 `response.output_text.delta` 变成 `ModelTextDelta`；
- 完整的 function call output item 解析 arguments，变成 `ModelToolCall`；
- `response.completed` 经过终态校验后变成 `ModelCompleted`；
- created、in_progress 等没有内部意义的生命周期通知被明确忽略；
- refusal、failed、incomplete 和 error 转换为安全的 `ModelProviderError`；
- 未列入支持范围的事件或输出类型失败关闭。

文本和函数参数共同计入 4,000,000 字符的聚合上限。限制聚合大小而不只限制单个 delta，才能阻止
很多小片段累积成无限输出。

## 为什么 completion 还要再核对一次 Tool call

流中已经发出的 Tool call 会记录 `provider_call_id`、name 和规范化 JSON 参数。看到最终 completion
时，`_validate_completion_tool_calls` 再比较最终 output：

- call ID 集合必须完全相同；
- 不能重复 call ID；
- Tool 名称不能改变；
- 参数按 key 排序并压缩后必须相同。

如果流中告诉 Runtime “读取 A”，completion 却把它改成“写入 B”，adapter 不接受任何一个版本为
事实。这个校验把 Provider 流当成不受信任输入，而不是假设同一次响应内部永远一致。

## 成功流必须只有一个明确终点

`terminal_seen` 保证 `ModelCompleted` 之后不能再出现事件。流自然结束却没有 completion，也会报告
协议错误。中途失败时，已经 yield 的文本片段可能已用于界面展示，但不会伪造 `ModelCompleted`。

`CancelledError` 原样向上传播，避免把调用方主动取消伪装成 Provider 普通失败。

## 外部异常怎样变成安全错误

`_classify_sdk_error` 把常见 SDK 和 HTTP 异常归一化：

| 外部情况 | 内部 code | 可重试提示 |
|---|---|---|
| timeout | `PROVIDER_TIMEOUT` | 是 |
| rate limit | `PROVIDER_RATE_LIMITED` | 是 |
| authentication / permission | 对应认证或权限 code | 否 |
| bad request | `PROVIDER_INVALID_REQUEST` | 否 |
| connection、429、5xx | unavailable/rate limit | 是 |
| 未知错误 | `PROVIDER_ERROR` | 否 |

公开 details 只保留长度受限的 request ID、Provider code 和数字 status。响应 body、Header、Prompt、
模型输出和原始异常文本不会复制进去。

## FakeModelProvider 为什么值得先读

`adapters/testing/model.py` 只有几十行：它回放预先配置的 `ModelEvent`，记录收到的内部请求，还能在
指定事件后抛出失败。它让 Runtime 测试无需网络就能稳定复现“输出两段文本后失败”等情况。

Contract test 又通过 `httpx.MockTransport` 让真正的 OpenAI SDK 解析内存 SSE。这样既测试官方 SDK
边界和请求 JSON，又不需要账号、API key 或在线模型。

建议阅读和运行：

```powershell
uv run pytest tests/unit/test_model_contracts.py tests/unit/test_testing_adapters.py
uv run pytest tests/contract/test_model_provider_contract.py
uv run pytest tests/security/test_model_provider.py
```

模型边界已经实现，但没有 ContextBuilder 决定放入哪些消息，也没有 Agent Loop 消费事件、保存
Model Activity 或把 Tool call 送入 `ToolExecutor`。不要把“adapter 能完成一次流式翻译”理解成
“CLI 已经能完成真实 Agent 任务”。
