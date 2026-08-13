---
title: "ADR-0007: BearAgent modules exchange BearAgent data types"
status: accepted
date: 2026-08-10
---

# ADR-0007：BearAgent 模块之间只交换 BearAgent 数据类型

## 要解决的问题

模型 adapter 收到 SDK 响应，Runtime 要推进状态，Event store 要保存 JSON，CLI 要展示错误。如果
这些模块直接交换字符串、任意字典或某个 Provider 的类，同一个 ID 和 Message 会出现不同字段，
更换 Provider 也会迫使 Runtime 跟着修改。

## 决定

模块边界只传 BearAgent 自己定义的 Pydantic v2 类型：

- 每种核心 ID 都是独立的 UUID4 类型，并由可替换的 `IdGenerator` 创建；
- Message 只包含 system、user、assistant、tool 角色，以及文本、工具请求和工具结果；
- Error 保存稳定 category、code、retryable 和经过筛选的安全详情；
- Event 通用字段包括 ID、sequence、版本、带时区时间和 JSON payload；
- 所有公开 model 冻结并拒绝未知字段，提交 JSON schema 快照用于审查变化。

Provider SDK 对象在对应 adapter 内翻译。Pydantic 只负责内部数据校验，不改变依赖方向：domain 和
Runtime 不得导入 Provider SDK、CLI 或数据库 adapter。

## 比较过的方案

- dataclass 加手写校验会重复实现联合类型、JSON 限制和 schema 生成；
- 继续使用字符串和字典会把歧义传播到所有 port；
- 直接采用第一个 Provider 的消息类型会减少一次翻译，却把整个 Runtime 绑定到该 SDK；
- UUID7/ULID 可排序，但 P1 不依赖 ID 排序，sequence 和时间已经承担该职责。

## 带来的影响

adapter 必须显式翻译外部数据，这是接受的样板成本。Provider 新字段不会自动进入 Runtime，旧 JSON
含义也能通过 schema 快照审查。UUID4 不提供时间顺序，业务排序必须使用 sequence 或 `occurred_at`。

## 怎样验证

单元测试覆盖合法与非法数据、角色组合、JSON 往返和冻结；安全测试覆盖敏感错误字段与外部对象
泄漏；契约测试比较已提交的 JSON schema 快照。
