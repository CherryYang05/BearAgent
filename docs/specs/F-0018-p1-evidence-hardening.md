---
title: "Feature: identify trusted Run contracts and expose committed crash boundaries"
status: implemented
spec_id: F-0018
milestone: P1
change_level: S2
owner: CherryYang05
created: 2026-08-28
last_updated: 2026-09-02
implemented_in: "commit 26f3203"
related_adrs: [ADR-0002, ADR-0003, ADR-0004, ADR-0007, ADR-0012, ADR-0013, ADR-0014, ADR-0016]
---

# F-0018：记录 Run 使用的可信执行契约，并展示进程中断前最后确认的事实

## 1. 问题与证据

P1 已保存模型请求、Tool 请求、PolicyDecision、ToolResult、Artifact 和预算事实，但一个历史 Run 只记录
Tool 名称和当次 Policy 结果。以后 Tool schema、`prepare` 规范化、资源限制或固定 Policy 配置变化时，
调用方无法从 `RunCreated` 判断当时使用的是哪一版可信 Tool/Policy contract。

现有 `tests/recovery/test_agent_loop_boundaries.py` 已证明 Event append 失败后不会重复模型或 Tool 调用，
也覆盖“`workspace.write` 已替换目标但 terminal Event 未保存”。这些测试仍运行在同一 Python 进程，
没有验证 SQLite/WAL、projection、workspace 和 CLI 在 hard process death 后共同呈现什么事实。

`ErrorInfo.retryable` 和 `ToolRetrySafety` 已用于描述错误来源及 Tool contract，但它们必须在进入 P2 前
明确保持为观察/声明信息，不能被未来代码直接当成恢复授权。

## 2. 目标与非目标

### 本次交付

- G-1：每个新 Run 在创建时保存可信、有限、非敏感且不可变的 `RunFingerprint`；
- G-2：为注册时 `ToolSpec` 增加显式 `spec_version`，并为 Tool/Policy contract 生成确定性 SHA-256；
- G-3：使用新的 `RunCreated` Event schema 保存 fingerprint，旧 Event 和 SQLite 数据继续可读；
- G-4：`inspect` 展示 fingerprint，Event 仍是事实来源，projection 不成为第二份真相；
- G-5：用测试和代码契约明确 `retryable`、`ToolRetrySafety` 不构成 RecoveryDecision；
- G-6：在真实子进程终止边界验证 K1-K6，只展示最后 committed fact，不补写结论。

### 本次不做

- NG-1：不增加 Attempt、Receipt、ExecutionPhase、RecoveryEvidence、RecoveryDecision 或 `UNKNOWN`；
- NG-2：不增加 retry、reconcile、resume、startup scan、Checkpoint 或 postcondition recovery；
- NG-3：不增加 Grant、Approval、三态 Policy、SandboxBackend、shell/code Tool 或新的权限入口；
- NG-4：不新增 `trace` CLI，不重构 causation/correlation public contract；
- NG-5：fingerprint 不保存完整实现、Git working tree、SDK/client、路径、secret、Prompt 或 Tool 输出；
- NG-6：不把本 Feature 扩成通用 AgentLoop、Reducer、Provider adapter 或 tracing 重构。

## 3. 场景与可观察行为

### 3.1 新 Run 保存执行契约身份

- FR-1：`RunFingerprint` 最终形状为 `bearagent_version`、一个 Policy fingerprint 和按 Tool 名称排序的
  Tool fingerprints；
- FR-2：Policy fingerprint 包含稳定 `version` 与 64 位小写十六进制 `sha256`；
- FR-3：每个 Tool fingerprint 包含 `name`、`spec_version` 与 `sha256`；Tool 名称必须唯一并稳定排序；
- FR-4：Tool hash 覆盖完整、序列化后的注册时 `ToolSpec`，包括 description、schema、副作用、timeout、
  输入/输出上限、retry safety 和 `spec_version`；
- FR-5：Policy hash 覆盖固定 evaluator version、排序后的 allowlist 与固定硬拒绝副作用集合；
- FR-6：相同语义输入使用 UTF-8、排序 key、紧凑 separators 的 canonical JSON，跨注册顺序得到同一 hash；
- FR-7：`spec_version` 负责标识 schema JSON 之外的行为 contract，例如 `prepare` 规范化或边界校验；
  这是一条人工版本纪律，hash 不声称自动覆盖 adapter 全部实现。

### 3.2 fingerprint 只提供有限 provenance

- FR-8：`bearagent_version` 使用已安装 BearAgent 包声明的版本；本地源码回退版本不声称能唯一定位 Git
  commit；
- FR-9：fingerprint 表示声明的 BearAgent build identity 与 Tool/Policy contract identity，不是完整历史
  代码快照、恢复证据、Grant、capability 或单次 PolicyDecision；
- FR-10：模型、Prompt、Skill、workspace、ToolResult 和 Provider 响应都不能提供或覆盖 fingerprint 字段。

### 3.3 failure hint 不触发恢复

- FR-11：`ErrorInfo.retryable` 只表示错误来源给出的 transient/retryable hint；
- FR-12：`ToolRetrySafety` 只描述可信 Tool contract 的粗粒度重试属性；
- FR-13：任一字段都不能授权 P1 发起第二次模型或 Tool 调用；Provider/Tool 返回 `retryable=true` 时，
  当前 Activity 仍按既有 P1 路径结束或交回模型，不产生隐藏 retry。

### 3.4 crash 后只展示已提交事实

- FR-14：K1 在 `ToolCallRequested` 提交后终止，重开后 Activity 为 `PENDING`，Tool 未执行；
- FR-15：K2 在 `ToolCallStarted` 提交后、adapter 进入前终止，重开后 Activity 为 `RUNNING`；
- FR-16：K3 在临时文件 fsync 后、`os.replace` 前终止，目标保持旧内容或不存在，且没有 Tool terminal Event；
- FR-17：K4 在 `os.replace` 后、ToolResult/Event 保存前终止，目标可能已更新，但 inspect 不宣称成功，
  不构造 Artifact，也不重试；
- FR-18：K5 在 Event insert/projection update transaction 提交前故障，重开后两者都不存在部分提交；
- FR-19：K6 在 `ModelCallStarted` 后终止，重开后不补 `ModelCallFailed`、usage 或第二次 Provider 调用；
- FR-20：测试可直接读取文件或调用 marker 作为 oracle，但 production Runtime 不把 oracle 转换成新 Event。

## 4. 对外入口与模块连接

`bearagent run` 参数不变。Production composition 从包版本、注册时 `ToolSpec` 和固定 Policy 的可信静态
配置构造 `RunFingerprint`，再注入 `AgentLoop`。Application 只接收 BearAgent domain 类型，不读取包元数据、
adapter 或本机路径。

```text
ToolRegistry specs ----┐
FixedToolPolicy -------+--> pure fingerprint builder --> RunFingerprint
package version -------┘                                  |
                                                           v
                                            AgentLoop -> RunCreated v4
                                                           |
                                                           v
                                            EventStore -> RunQueryService
                                                           |
                                                           v
                                                        inspect
```

`run events --json` 继续返回原始 Event envelope/payload；`inspect` 的 domain/CLI JSON 增加可选 fingerprint，
旧 Run 返回 `null`。Human inspect 显示完整版本和 hashes，不打印输入配置或路径。

## 5. 状态与持久化

- 新 Run 的全部 P1 Event 使用 schema v4；`RunCreatedPayloadV4` 在 v2 的 objective/AgentConfig 上增加
  `run_fingerprint`，并保留可选的非敏感 `provider_selection`；
- 使用 v2 execution evidence shape 的 Tool terminal Event（当前为 schema v2/v3/v4）必须与同版本
  `ToolCallRequested` 中的原始 `ToolRequest` 值相等；Reducer 按解析后的 payload shape 执行这条跨 Event
  校验，不能靠列举旧版本号决定是否校验；
- Event v1/v2/v3 payload 含义不变并继续由相同 registry 解析；
- Reducer 从任意受支持 `RunCreatedPayload` 取得 Session/预算，`RunState` 与 SQLite projection schema 不增加
  fingerprint 字段；
- SQLite 继续把 v4 payload 写入现有 `payload_json`，不修改 `0001_initial.sql`，不增加 migration；
- query service 从 sequence 1 的 committed `RunCreated` 提取 fingerprint/provider selection；缺失表示 legacy
  Run，不从当前 Registry/Policy 反推历史值。

## 6. 失败、恢复与安全边界

- canonicalization 只接受 domain 已验证的 JSON；禁止 `repr()`、对象地址、注册顺序和本机环境进入 hash；
- fingerprint 类型只允许有界版本字符串、Tool 名称和 SHA-256，不提供能承载任意配置的详情字段；
- security tests 使用 marker 扫描 Event 与 inspect JSON，确认 API key、authorization、cookie、credential、
  password、secret、token、Provider repr、workspace/database 绝对路径均未进入；
- fingerprint 合法与否不改变 Policy 结果；执行仍只经过 Registry -> prepare -> Policy -> Executor；
- crash suite 使用子进程 `os._exit` 和确定性 marker，不使用 `sleep` 猜测时序；结束后用新的 SQLite adapter
  与 CLI 进程读取；
- K3/K4 的测试 seam 位于测试 adapter/wrapper，不把 test hook、ExecutionPhase 或 recovery state 加入生产
  domain；
- hard exit 后不自动清理临时文件，不扫描非终态 Run，也不追加任何 Event。

## 7. 上线与回退

没有 feature flag 或 SQL migration。新代码先增加 v4 读取，再让 AgentLoop 写 v4。上线后可以停止创建新
Run，但不能删除 v4 payload/fingerprint 读取代码。回退不得修改历史 Event、数据库、Artifact 或
`outputs/**`。

若 fingerprint 实现需要回退，可保留 v4 parser/query 兼容并停止新 Run 入口；不能把旧 Run 用当前配置
重新计算成看似真实的历史 fingerprint。

## 8. 验收标准与证据

| AC | 可判断的结果 | 证据路径或命令 |
|---|---|---|
| AC-1 | 相同 Tool/Policy contract 跨顺序产生相同 hash，任一声明字段变化会改变对应 hash | `tests/unit/test_run_fingerprints.py` |
| AC-2 | 新 Run 写 v4 fingerprint；旧 v1/v2/v3 Event 与 SQLite 继续读取 | domain/store/query contract tests |
| AC-3 | inspect human/JSON 展示新 fingerprint，legacy Run 显示缺失而非伪造 | CLI/query tests |
| AC-4 | fingerprint 不包含 secret、路径、Provider client，也不能扩大 Policy | security tests |
| AC-5 | `retryable=true` 和 `ToolRetrySafety` 都不产生自动第二次调用 | AgentLoop/ToolExecutor recovery tests |
| AC-6 | K1-K6 在 Windows/Linux 可重复运行并断言 Event、projection、文件、CLI 与调用 marker | `tests/recovery/test_crash_observability.py` |
| AC-7 | K4 文件已变化但没有 Tool terminal/Artifact/伪成功，也没有 retry/reconcile | crash observability K4 |
| AC-8 | Event/projection transaction 故障后重开无部分提交 | crash observability K5 + SQLite tests |
| AC-9 | core/application import 边界、schema、治理、docs、site、package build 和全量测试通过 | 最终验证命令 |
| AC-10 | 代码与文档没有新增任何 P2/P3 domain 类型或行为 | diff review + governance/docs checks |
| AC-11 | v2/v3/v4 Tool terminal evidence 都不能把 requested Event 中的原始 ToolRequest 替换成另一请求 | Reducer unit + memory/SQLite Store contract tests |

## 9. 文档影响

| 表面 | 更新路径，或 `N/A` + 原因 |
|---|---|
| Engineering `docs/` | 本 Spec、ADR-0016、Plan、Roadmap、Architecture、Spec/ADR/Plan indexes |
| Site beginner path | 更新 `learn/run-inspect-events.md`，解释 fingerprint 与 crash 后最后 committed fact |
| Site developer docs | 更新 AgentLoop/EventStore/Tool contract 相关页面，说明 v4 与 canonical identity |
| Site current status | 更新 `project/status.md`，只声明 evidence hardening，不声明 crash recovery |
| Generated reference | 更新 domain/CLI Schema snapshots；SQLite migration N/A，因为只复用 Event JSON |

## 10. 尚未决定的问题

- OQ-1：N/A。字段、兼容、hash 与 crash harness 边界已由 ADR-0016 决定；实现发现新恢复需求时记录为
  P2 Feature，不扩大本 Spec。

## 11. 完成后维护记录

2026-09-02 的 P1 全仓审计发现：`validate_event_history` 曾用 `{2, 3}` 决定是否核对 Tool terminal
evidence，导致 F-0018 新增的 schema v4 绕过同一条原始请求一致性检查。修复改为先解析 payload，再按
`ToolCallCompletedPayloadV2` / `ToolCallFailedPayloadV2` shape 决定是否检查；v2/v3/v4 共用同一组
Reducer 与两个 Store contract 用例。该修复只拒绝不可信的矛盾历史，不增加 retry、reconcile、恢复或
授权语义。
