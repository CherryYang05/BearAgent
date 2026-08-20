---
title: F-0004 ModelProvider 实现导读
description: OpenAI Responses 适配器的内部数据规则、翻译边界、失败规则与测试证据。
bearStatus: implemented
sourceRefs:
  - F-0004
  - ADR-0010
  - PLAN-F-0004
---

F-0004 只交付模型边界，不包含 Agent Loop。它把官方 SDK 限制在适配器目录，并让核心代码只依赖
BearAgent Pydantic 数据模型与 `ModelProvider` 内部接口。

这里的 Port 是核心代码调用的内部接口，Adapter 是对外部协议的翻译实现；JSON Schema 是可生成、
可比较的数据格式说明。三者分别回答“核心怎样调用”“外部怎样接入”和“数据允许长什么样”。

## 代码地图

| 范围 | 入口 | 责任 |
|---|---|---|
| 内部数据 | `src/bearagent/domain/model.py` | 请求、工具定义、流事件、用量、资源上限 |
| Message | `src/bearagent/domain/messages.py` | BearAgent 与模型服务商的工具调用身份 |
| 内部接口（Port） | `src/bearagent/ports/model.py` | 流式接口与安全 `ModelProviderError` |
| 生产适配器 | `src/bearagent/adapters/model/openai_responses.py` | Responses 请求、SSE 和错误翻译 |
| 确定性替代实现 | `src/bearagent/adapters/testing/model.py` | 预设流式事件与中途失败 |

## 关键边界

- `domain/`、`runtime/`、`ports/` 不导入 `openai`；SDK 类型只存在于适配器。
- 客户端使用 `max_retries=0`；每个请求显式传入有限超时、`store=false` 与
  `parallel_tool_calls=false`。
- 适配器只允许已支持的文本、函数调用和模型完成过程；托管工具、音频、图像、MCP
  或其他输出项都会安全失败。
- Aggregate text/arguments 有字符上限；函数参数必须解析为有界 JSON object。
- `response.failed`、`response.incomplete`、SSE error 与 SDK exception 都转换为安全 ErrorInfo，
  不复制响应 body、header、prompt、输出或原始异常文本。
- `CancelledError` 原样传播；流式响应中途失败时不产生模型完成事件。

## 测试证据

`tests/contract/test_model_provider_contract.py` 使用 `httpx.MockTransport` 让官方 SDK 解析内存 SSE，
同时检查发出的请求 JSON。这样验证了 SDK 边界，却不依赖网络、账号或 API key。

`tests/security/test_model_provider.py` 覆盖 400/401/403/429/500、超时、流式响应中途失败、取消与
包含敏感信息的响应；`tests/unit/test_model_contracts.py` 覆盖数据格式、深层不可变、历史关联与
资源上限。公共 JSON Schema 快照同步保存了 F-0004 的内部数据规则。

真实账号与模型可用性不属于默认 CI 证据。F-0016 已由 Agent Loop 把模型完成用量和安全错误转换成
持久 Model Activity Event；F-0005 再组装生产 adapter 并提供用户可运行的 CLI。
