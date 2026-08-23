---
title: 从数据边界开始读代码
description: 沿 ID、Message、Error 和 Event 理解 BearAgent 为什么先约束内部数据，再连接模型、存储和 Tool。
bearStatus: implemented
sourceRefs:
  - F-0001
  - F-0004
  - F-0006
  - domain schema snapshot
---

先看一个最容易被忽略的错误。假设模型返回了工具参数：

```python
{"path": "docs/index.md", "options": {"encoding": "utf-8"}}
```

如果 Runtime 直接保存这个普通 `dict`，调用方仍可以在记录之后修改 `options`。Event 表面没有变，
里面的事实却变了。BearAgent 因此不只把 Pydantic model 设为 `frozen=True`，还会复制并递归冻结
嵌套的 JSON 对象。

理解这一点后，再读 `domain/` 就不会把它看成一堆“只为类型提示存在的 class”。这些类是模型、
Runtime、数据库和 Tool 之间共同遵守的数据边界。

## 第一站：`DomainModel` 定下共同规则

打开 `src/bearagent/domain/_base.py`，先看 `DomainModel`：

```python
model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)
```

三项配置分别意味着：未知字段不能悄悄混入，实例建立后不能直接赋值，默认值也必须经过验证。
同一文件里的函数继续处理 Pydantic 默认不会替你解决的问题：

- `validate_json_object` 只接受真正的 JSON object；
- 深度最多 32 层，节点最多 10,000 个，防止极端嵌套拖垮边界校验；
- `freeze_json_mapping` 把字典变成只读映射，把列表变成 tuple；
- `thaw_json_mapping` 只在序列化时恢复为普通 JSON 容器。

阅读其他 domain 文件时，看到 `mode="before"` validator、冻结 validator 和 serializer 连在一起，
就是这套“先限制、再冻结、输出时还原”的固定模式。

## 第二站：ID 的类型表达“这个 UUID 是谁”

`domain/ids.py` 中的 `RunId`、`EventId`、`ToolCallId` 底层都是 UUID4，但它们不是可互换的字符串。
函数要求 `RunId` 时，传入 `EventId` 会被类型检查和模型校验及时发现。

`Uuid4IdGenerator` 又把“产生随机 ID”放到可替换对象后面。生产环境使用 UUID4，测试可以控制生成
顺序，核心逻辑不必自己调用随机函数。

建议同时读 `tests/unit/test_ids.py`：

1. 看 `new()` 和 JSON 往返怎样工作；
2. 看不同 ID 子类为什么不可互换；
3. 看非 UUID4 和无效文本怎样在入口失败。

## 第三站：Message 约束对话的合法形状

`domain/messages.py` 把一条消息拆成 role 和 part：

| role | 允许的内容 |
|---|---|
| `system`、`user` | 只能包含非空文本 |
| `assistant` | 文本和 Tool call，不能包含 Tool result |
| `tool` | 必须且只能包含一个 Tool result |

`ToolCallPart` 同时保存两种身份：

- `tool_call_id` 是 BearAgent 自己的稳定关联 ID；
- `provider_call_id` 是模型服务商用来把调用与结果对上的 ID。

把两者分开，才能在内部持久化、重放或更换 Provider 时保留 BearAgent 的身份，同时在回传历史给
Provider 时恢复对方需要的 call ID。

`Message.validate_role_parts` 还会拒绝 assistant 中重复的 `tool_call_id`。这不是格式洁癖：如果两个
请求共用一个 ID，后面的 Tool result 就无法明确对应哪一个动作。

## 第四站：Error 只保留可以公开的内容

外部异常经常包含 URL、请求体、路径、Header，甚至密钥。`domain/errors.py` 因此把内部异常和对外
数据分开：

- `ErrorInfo` 是可保存、可展示的数据；
- `BearAgentError` 可以用 `__cause__` 保留 Python 原始异常，供本地调试；
- 对外只使用稳定的 `category`、`code`、`message`、`retryable` 和有限 `details`。

`details` 的 key 如果包含 `token`、`authorization`、`cookie`、`password`、`secret` 等片段，会直接
被拒绝。值的类型、数量和长度也有限制。这样 adapter 即使拿到了复杂异常，也不能顺手把整段原始
响应塞进公开错误。

重点阅读 `tests/security/test_domain_errors.py`。它不是只测正常构造，而是主动尝试敏感 key、非有限
浮点数、过长数据和 category/code 错配。

## 第五站：Event 是事实的统一信封

`domain/events.py` 中的 `Event` 不直接定义“模型完成”或“Tool 失败”的全部字段，而是提供统一外壳：

```text
event_id          这条事实自己的身份
run_id            它属于哪个 Run
sequence          在这个 Run 中的严格顺序
event_type        事实类型
schema_version    payload 的版本
occurred_at       带时区并规范到 UTC 的时间
causation_id      谁直接导致了它
correlation_id    它属于哪条诊断链路
payload           有界且递归冻结的 JSON 数据
```

具体 Run Event 的 payload 在 `domain/run_events.py`，由 `parse_run_event_payload` 按
`(event_type, schema_version)` 找到精确类型。未知类型和未知版本不会被“尽量解析”，而是失败关闭。

## 为什么还要保存 JSON Schema 快照

`domain/schema.py` 收集对外稳定的数据模型，脚本把生成结果写入
`tests/contract/snapshots/domain_schemas.json`。Contract test 比较当前生成结果和快照。

快照不是为了禁止修改，而是让修改变得可见。新增必填字段、改变枚举值或放宽输入后，评审者会在
diff 中看到公共数据形状发生了什么变化，而不是等旧数据库或 adapter 运行时才发现。

## 一次修改的正确阅读顺序

要修改 Message、Error 或 Event 时，建议按这条路线走：

1. 从对应 unit/security test 找到当前可观察行为；
2. 回到 `domain/` 看 validator 和 model-level 组合规则；
3. 搜索类型的所有调用方，尤其是 adapter 的翻译代码和 SQLite 序列化；
4. 判断已保存 JSON 的含义是否变化；
5. 重新生成 schema，但先审查 diff 再接受快照。

常用验证命令：

```powershell
uv run pytest tests/unit/test_ids.py tests/unit/test_messages.py tests/unit/test_events.py
uv run pytest tests/security/test_domain_errors.py
uv run pytest tests/contract/test_domain_schemas.py
uv run pyright
```

这些类型已经被状态、SQLite、模型、Tool、AgentLoop 和 CLI 共用。下一步可以沿
[Event 怎样改变状态](run-reducer-and-budgets.md)，继续看这些数据进入 Runtime 后发生什么。
