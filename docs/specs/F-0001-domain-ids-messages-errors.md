---
title: "Feature: Domain IDs, messages and errors"
status: implemented
spec_id: F-0001
milestone: P1
owner: CherryYang05
created: 2026-08-10
last_updated: 2026-08-13
implemented_in: "PR #2"
related_adrs:
  - ADR-0001
  - ADR-0002
  - ADR-0007
---

# F-0001：统一内部 ID、Message、Error 和 Event 外壳

## 1. 为什么现在要做

P0 用字符串 ID、字符串消息和最小 Event 支撑测试。如果 Run、模型、存储、Tool 和 CLI 继续各自
定义字典，同一个概念会出现不同字段，模型 SDK 类型也会进入 Runtime，旧 JSON 很难保持兼容。

F-0001 先规定 BearAgent 模块之间交换哪些数据。外部系统在 adapter 处翻译，Runtime 不接收 SDK
response 或数据库对象。

## 2. 本次交付

- G-1：不同领域对象使用不同的 UUID4 ID 类型，并能替换 ID 生成器；
- G-2：定义只含文本、工具请求和工具结果的 Message；
- G-3：定义可以安全进入 CLI、Event 和日志的 Error；
- G-4：补全不可变、带版本的 Event 通用字段；
- G-5：提交公共类型的 JSON schema 快照，用于审查兼容性变化。

## 3. 本次不做

Run 状态、Reducer、预算、SQLite、恢复、真实模型、Tool、文件访问和 Run CLI 均不在本 Feature。
Message 暂不支持图片、音频或其他多模态内容。具体 Event payload 由后续 Feature 添加。

## 4. 需要先说明的约定

ID 是不透明值，代码不能依赖 UUID 文本排序或时间含义。安全 Error 只保存稳定摘要，不含原始异常、
堆栈、凭证和完整敏感输入。P1 Message 只覆盖文本 Agent Loop 需要的内容。

## 5. 使用场景

### 同一个 Run 跨模块传递

Application 创建 Run 后，存储、模型和 CLI 都使用同一个 `RunId` 类型。把 `ActivityId` 传入需要
`RunId` 的位置应被类型或运行时校验发现。

### 模型响应进入 Runtime

模型 SDK 返回工具调用后，adapter 把它转换成 BearAgent Message。Runtime 只看到内部 part，并用
`ToolCallId` 把后续结果关联回请求。

### 错误安全传播

外部调用抛出异常后，adapter/application 创建稳定 Error，只保留 category、code、retryable、
message 和筛选后的上下文；原始异常不进入序列化数据。

## 6. 必须满足的行为

- FR-1：定义 Session、Run、Activity、Event、Artifact、ModelCall、ToolCall、Causation、Correlation ID；
- FR-2：ID 只接受 UUID4，生产代码通过可替换 `IdGenerator` 创建；
- FR-3：Message role 只允许 system、user、assistant、tool；
- FR-4：Message part 使用可区分的 text、tool_call、tool_result 类型；
- FR-5：system/user 只含文本，assistant 含文本或工具请求，tool 只含工具结果；
- FR-6：Error category 至少覆盖 validation、budget、provider、tool、persistence、internal；
- FR-7：Error detail 拒绝常见敏感字段，并限制文本和容器大小；
- FR-8：Event 包含 ID、Run、sequence、类型、版本、时间、causation、correlation 和 JSON payload；
- FR-9：公共 model 拒绝未知字段、实例冻结并可序列化为 JSON 基础类型。

## 7. 对外入口和模块连接

```text
domain.ids       各种 ID + IdGenerator
domain.messages  Message role + Message parts
domain.errors    Error category/code/info + BearAgentError
domain.events    所有 Event 共用的外壳
```

这些是 BearAgent 内部接口，不承诺作为第三方 Python SDK。Provider adapter 和存储 adapter 都要
显式翻译外部数据。

## 8. 状态和保存的数据

ID 写成规范化的小写连字符 UUID。Event sequence 和 schema version 从 1 开始，时间必须带时区并
规范化为 UTC。payload 只能包含 JSON 值。F-0003 再决定 SQLite 列、索引、transaction 和 migration。

## 9. 失败时会发生什么

非 UUID4、空 Message、非法 role/part、无时区时间、非 JSON payload 和未知字段都在构造入口失败，
不自动重试。`BearAgentError.__str__` 只显示安全 message；原始异常只可作为 Python cause。
本 Feature 没有崩溃恢复。

## 10. 安全与隐私

Message、Event payload 和 Error detail 都按不可信输入校验。Error detail 拒绝 authorization、cookie、
password、secret、token、api_key 等键。领域类型不包含 SDK response、认证头和原始 exception。

结构限制只能减少误泄露，调用方仍不得把密钥写进普通 message 文本。

## 11. 怎样检查执行过程

Event 的 Run、correlation、causation 和 sequence 为后续查询提供关联；Error 的 category、code 和
retryable 可直接聚合，不需要解析自由文本。

## 12. 上线与回退

没有持久数据库，P0 测试类型可以一次性替换。回退代码和 lockfile 即可。F-0003 建立持久 schema
后，不兼容 Event 变化必须使用新版本和迁移/upcaster。

## 13. 验收标准

- AC-1：每种 ID 可创建、JSON 序列化并按具体类型比较；非法 UUID 失败；
- AC-2：合法 Message 可 JSON 往返，非法 role/part 失败；
- AC-3：Error 提供稳定字段，敏感键、未知字段和超限内容失败；
- AC-4：Event 具有全部通用字段，非法 sequence、无时区时间和非 JSON payload 失败；
- AC-5：domain 不导入 Provider SDK、Typer、SQLite 或 adapter；
- AC-6：ID、Message、Error 和 Event schema 与提交快照一致；
- AC-7：Fake model/store 和 ports 使用新类型，原有行为测试继续通过。

## 14. 验证方式

- Unit：ID、消息组合、Error 限制、Event 校验和 JSON 往返；
- Contract：公共 JSON schema 快照；
- Integration：P0 Fake model/store 使用新类型；
- Security：敏感 Error 键、未知字段、非 JSON payload 和 Provider 类型泄漏；
- Recovery/Eval：不适用。

## 15. 文档同步

- [x] Engineering docs
- [x] Architecture / ADR
- [x] Site learning path
- [x] Site developer guide
- [x] Site status
- [x] Generated schema snapshot

## 16. 尚未决定的问题

无。UUID4、消息范围和 Error 安全边界已确认。
