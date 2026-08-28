---
title: "ADR-0016: persist trusted Run contract identity and report only committed crash facts"
status: accepted
date: 2026-08-28
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0016：Run 创建时保存可信契约身份，进程中断后只报告已提交事实

## 要解决的问题

P1 已经保存一次调用的请求、PolicyDecision 和结果，却没有保存 Run 启动时注册的 Tool/Policy contract
identity。同名 Tool 或固定 Policy 以后改变时，历史 Event 仍可读取，但读者无法判断当时使用了哪套声明。

同时，现有异常注入测试能证明 Loop 不重试，却不能证明进程 hard exit 后 SQLite、projection、workspace 和
CLI 对“最后确认知道什么”保持一致。如果为方便查询把 fingerprint 放进 projection，或让 crash 测试根据
文件现状补写成功，都会产生第二份事实来源并提前进入 P2 recovery。

## 选择时最看重什么

- 可维护性：复用 Domain Value Object、现有 ToolRegistry/Policy 和 Event schema，不建立第二套配置或 registry；
- 恢复语义：P1 只保存 identity 与 committed boundary，不根据 hint/目标状态决定下一步；
- 安全：fingerprint 只能来自可信静态注册信息，不能承载 secret、路径、Prompt、输出或权限 token；
- 复杂度/交付时间：使用标准库 JSON/SHA-256 和测试 wrapper，不引入依赖、生产 fault framework 或 DB 表；
- 兼容与迁移：旧 Event/SQLite 只读语义不变，新事实使用 v4 payload JSON。

## 比较过的方案

### 方案 A：只保存包版本和 Tool 名称

字段少，但同一版本内 Tool schema、资源上限、Policy allowlist 或 prepare contract 不同仍无法区分；包版本
也不能精确表达每个声明内容。

### 方案 B：在每个 Tool Event 保存完整 ToolSpec 和 Policy 配置

查询直接，但重复大量 JSON；单次 Event 与 Run 启动 contract 可能分叉；未来动态 Approval 也容易被误塞
进静态 identity。

### 方案 C：RunCreated 保存版本化 fingerprint，Event 保持事实来源

ToolSpec/Policy 静态 contract 使用 canonical JSON + SHA-256；Run 创建时一次保存。Query 从首个 Event
读取，legacy Run 明确缺失。hash 只标识声明，不声称包含全部实现。

### 方案 D：建立 fingerprint/projection 数据表

读取快，但引入 migration 和新的事实真相；表与 Event 分叉后难以判断哪份可信，收益不抵复杂度。

## 决定

选择方案 C，并确定以下规则：

1. Domain 增加冻结的 `PolicyFingerprint`、`ToolFingerprint` 和 `RunFingerprint`。hash 固定为 64 位小写
   SHA-256，Tool 列表按名称排序且唯一。
2. `ToolSpec` 增加显式 `spec_version`。hash 覆盖序列化后的完整 ToolSpec；schema 外的 prepare/validation
   行为变化必须人工提升 `spec_version`。
3. `FixedToolPolicy` 暴露可信 fingerprint。canonical contract 覆盖 evaluator version、排序 allowlist 和
   固定 hard-denied side effects；它不包含单次请求、PolicyDecision、Grant 或 Approval。
4. canonical JSON 使用 UTF-8、`sort_keys=True`、紧凑 separators 与 JSON domain 值；禁止 `repr()`、对象
   identity、路径或注册顺序。
5. Composition root 使用声明的 BearAgent package version、Registry snapshot 与 Policy fingerprint 构造
   `RunFingerprint`，再作为必需 BearAgent 类型注入 AgentLoop。Application 不读取包元数据或具体 adapter。
6. 新 Run 统一写 Event schema v4。`RunCreatedPayloadV4` 保存 fingerprint 和可选 Provider selection；其他
   v4 payload 继续复用 v2 的 Provider-neutral shape。v1/v2/v3 永久可读。
7. fingerprint 只存在于 `RunCreated` Event。`RunState`/SQLite projection 不增加字段；inspect 从 committed
   Event 提取，legacy Run 返回 `null`，绝不按当前 Runtime 配置反推。
8. `ErrorInfo.retryable` 是来源 hint；`ToolRetrySafety` 是粗粒度 contract hint。二者都不是
   RecoveryDecision，也不能单独触发自动调用。
9. K1-K6 crash tests 使用真实子进程、SQLite 和 production-compatible AgentLoop/Tool 路径。测试 wrapper 可
   在精确边界写 marker 后 `os._exit`；生产代码不新增 durable phase、reconcile 或 fault hook contract。
10. 文件 hash/marker 只作为测试 oracle。即使 K4 的目标已更新，只要 terminal Event 未提交，query/CLI 就
    只能报告 Tool Activity `RUNNING`，不得补写 ToolCompleted、Artifact、RunSucceeded 或 `UNKNOWN`。

`bearagent_version` 是声明的 build/package identity。本地 `0.1.0+local` 不足以唯一定位 Git commit，文档和
CLI 不得把它称为完整代码 provenance；Tool/Policy hashes 只精确标识其声明 contract。

## 带来的影响

### 得到的好处

- 历史 Run 可以说明使用了哪套声明的 Tool/Policy contract；
- 注册顺序或进程变化不影响 identity，声明变化可见；
- 新事实沿用 Event/version/compatibility 机制，不引入表级双写；
- crash suite 为 P2 提供可信基线，同时不伪造恢复能力；
- 移除 AgentLoop 对 v2/v3 新 Run 构造的运行期分支，版本选择更集中。

### 接受的代价

- 每个 Tool contract 行为变化需要维护 `spec_version`；漏升版本无法由 hash 自动发现；
- Pydantic 生成 schema 的描述性变化也会改变 Tool hash，这是 declared contract identity 接受的保守变化；
- inspect 读取完整有界 Event 历史后才能返回 fingerprint，当前 P1 查询上限继续适用；
- 子进程 crash 测试比进程内异常注入更慢，并需要维护 Windows/Linux 一致入口；
- v4 一旦写入，历史读取代码不能删除。

## 迁移和回退

SQLite schema v1 和 `0001_initial.sql` 不变。先部署 v4 parser/schema/query，再让 AgentLoop 创建 v4。旧
Run 没有 fingerprint 时返回缺失，不迁移、不补写。

回退时可以停止新 Run 创建或恢复旧入口，但必须保留 v4 payload/fingerprint 解析。不得修改历史 Event、
projection、Artifact 或输出文件，也不得用当前配置生成伪历史 identity。

## 怎样验证

- canonical hash 的顺序稳定、字段敏感、跨进程和 schema snapshot 测试；
- Event v1-v4 在内存与 SQLite contract suite 中得到相同 P1 projection；
- production composition/new Run/inspect/CLI 测试证明 fingerprint 来自可信注册信息且不含 secret/路径；
- Provider/Tool `retryable=true` 调用计数测试证明没有自动 retry；
- K1-K6 子进程测试核对 Event 序列、projection、workspace hash、CLI 输出和调用 marker；
- import boundary、Ruff、Pyright、全量 pytest、schema、governance、docs、site 和 package build。
