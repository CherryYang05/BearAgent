---
title: "Feature: Unified Tool registry, executor, and fixed P1 policy"
status: implemented
spec_id: F-0006
milestone: P1
owner: CherryYang05
created: 2026-08-13
last_updated: 2026-08-14
implemented_in: "codex/F-0006-tool-executor-policy"
related_adrs:
  - ADR-0004
  - ADR-0005
  - ADR-0007
  - ADR-0009
---

# F-0006：所有 Tool 请求经过同一个执行和权限入口

## 1. 为什么现在要做

假设模型说：“请用 `workspace.read` 读取 `docs/index.md`。”现在 BearAgent 已经能收到这个 Tool 名称和
参数，但还没有一扇统一的执行入口。调用代码可以直接找到一个 Tool 并运行，也就没有一个固定位置
回答下面四个问题：

1. 这个 Tool 真的存在吗？
2. 参数合法吗，路径是否已经整理成唯一形式？
3. 当前 Runtime 允许它执行吗？
4. 如果它卡住、报错或返回几百 MB 内容，怎样安全结束？

F-0006 先把这扇门建起来。它暂时不提供真实文件 Tool。F-0007 和 F-0008 以后只需要把具体 Tool
接到这扇门上，不再各写一套权限和超时逻辑。

## 2. 本次交付

- 一份 Tool 名单。`ToolRegistry` 保存已注册 Tool，并按完整名称查找；
- 一张 Tool 说明卡。`ToolSpec` 写清参数格式、结果格式、副作用、超时和输入/输出上限；
- 一道固定权限门。P1 `Policy` 默认拒绝，只允许程序启动时明确列出的 Tool；
- 一个执行入口。`ToolExecutor` 负责检查、授权、限时调用和整理结果；
- 一组不访问真实文件或网络的测试 Tool，用来稳定复现成功和各种失败。

## 3. 本次不做

- 不读写真实文件。读取和搜索属于 F-0007，写入 `outputs/**` 属于 F-0008；
- 不接 Agent Loop、Event 或 CLI。它们仍由 F-0016 和 F-0005 完成；
- 不做用户审批。P1 没有 Grant、`ASK` 或 Approval；
- 不提供 shell、代码执行、任意网络 Tool、MCP 或自动发现插件；
- 不自动重试，也不加入 Attempt、Receipt、Checkpoint 或 `UNKNOWN`；
- 不修改 SQLite，也不改变已经发布的 v1 Run Event 格式。

## 4. 需要先说明的约定

下面几个英文名会直接出现在代码中：

- `ToolRegistry` 是 Tool 名单；
- `prepare` 是执行前的纯检查。它可以整理参数，但不能读文件、联网或产生其他副作用；
- `Policy` 是权限门，只回答允许还是拒绝；
- `ToolExecutor` 是唯一执行入口；
- `ToolSpec` 是可信 Tool 自带的说明卡，不是模型授予自己的权限。

一次请求只走下面这条短路径：

```text
模型给出 Tool 名称和 JSON 参数
  -> Registry 按精确名称查找
  -> Tool.prepare 只校验并规范化，不产生外部副作用
  -> Policy 根据可信配置和规范化参数返回 ALLOW 或 DENY
  -> Executor 在 timeout 和输出上限内调用 Tool.execute
  -> 返回成功数据或安全 ErrorInfo
```

P1 的 Policy 只有 `ALLOW` 和 `DENY`。允许名单来自程序启动配置；模型、Prompt、工作区内容和 Tool
返回值都不能改它。Tool 可以说明未来是否适合重试，但当前 Executor 每个请求最多调用一次。

## 5. 使用场景

### 正常请求

Tool 已注册、在允许名单中，参数也合法。Executor 调用它一次，并把结果和原来的 `ToolCallId`
放在一起返回。

### 名字不存在或没有权限

Executor 直接返回失败。Tool 的执行方法不会被调用，也不会尝试找“名称相近”的另一个 Tool。

### 路径有多种写法

以后的文件 Tool 会先在 `prepare` 中把路径整理成唯一形式。Policy 看到整理后的路径，再决定是否
允许。这样不会出现“检查的是一个路径，实际打开的是另一个路径”。

### Tool 卡住或返回太多内容

Executor 到达 timeout 后结束本次调用；结果超过上限时整次调用失败。它不会悄悄截断结构化数据，
也不会自动再调用一次。

## 6. 必须满足的行为

### 名称和数据要可控

- Tool 名称使用项目已有的统一格式；
- 参数、说明卡和结果都是大小、嵌套深度和节点数量有限的 JSON object；
- BearAgent 收到数据后会复制并冻结，外部代码不能事后修改；
- 请求、规范化请求和结果都带同一个 `ToolCallId`，防止把结果接到错误请求上。

### Registry 只做精确查找

- 启动时发现重名 Tool，Registry 立即失败；
- Tool 按名称稳定排序，方便测试和生成模型可见的说明；
- 找不到名称时直接失败，不猜测、不模糊匹配、不调用默认 Tool。

### 先检查参数，再检查权限

- `prepare` 必须先运行，并且不能产生外部副作用；
- `prepare` 失败后，不再调用 Policy 或 Tool；
- Policy 只看整理后的参数；
- Policy 默认拒绝，名称必须出现在可信允许名单中；
- P1 即使允许了名称，也永远拒绝外部写入和代码执行类别。

### Executor 负责收住失控调用

- 一个请求最多调用 Tool 一次；
- 每个 Tool 都有有限 timeout，以及最大输入和输出字节数；
- 调用者主动取消时，取消信号原样向上传递；
- Tool 抛出的异常只变成安全错误，不包含异常类型、堆栈、密钥或完整输出；
- 结构化结果超过上限时整次失败，不把半截 JSON 当作成功。

失败原因使用稳定代码：

| 发生了什么 | 返回代码 | Tool 是否执行 |
|---|---|---|
| 名称未注册 | `tool_not_found` | 否 |
| 参数不合法 | `tool_invalid_input` | 否 |
| Policy 拒绝 | `tool_permission_denied` | 否 |
| 调用超时 | `tool_timeout` | 已调用一次 |
| 结果过大 | `tool_output_too_large` | 已调用一次 |
| Tool 抛出其他异常 | `tool_error` | 已调用一次 |

这些错误在 P1 都不会自动重试。Tool 数据、Policy 结果和错误代码进入公共 JSON Schema。Runtime
仍然只能依赖 BearAgent 类型和 port，不能导入具体文件 Tool、Provider SDK、CLI 或数据库 adapter。

## 7. 对外入口和模块连接

实现后，代码按职责放在下面几个位置：

| 位置 | 负责什么 |
|---|---|
| `domain.tools` | Tool 的说明、请求、结果和权限决定长什么样 |
| `ports.tools` | 具体 Tool 必须提供 `prepare` 和 `execute` |
| `ports.policy` | Policy 必须能对规范化请求作出允许或拒绝决定 |
| `runtime.tool_registry` | 保存和查找已注册 Tool |
| `runtime.policy` | 实现 P1 固定权限规则 |
| `runtime.tool_executor` | 串起查找、检查、权限和执行 |

F-0016 以后会把模型给出的 `ModelToolCall` 转成 `ToolRequest`，交给 `ToolExecutor`，再把结果写成
Tool Activity Event 并交回模型。F-0007/F-0008 负责注册真实文件 Tool。

本 Feature 不增加 CLI/API，也不让 Runtime 直接导入具体 Tool adapter。

## 8. 状态和保存的数据

F-0006 自己不保存数据。Executor 完成一次调用后，只把结果返回给调用方。它不增加 Run 状态、Event、
SQLite 表或数据库升级脚本。

F-0016 接入 Agent Loop 时，才负责把 Tool 请求、开始和结束写进 Event。现在已经存在的 v1 Tool
Event 保持原样；以后要保存完整参数和结果时，新增 v2，不能偷偷改变旧 Event 的含义。

## 9. 失败时会发生什么

- 名称不存在、参数不合法或 Policy 拒绝时，Tool 还没开始，因此不会产生外部动作；
- Tool 超时后，本次调用结束，P1 不会自动再试；
- Tool 主动报告失败时，Executor 保留经过检查的安全错误；Tool 直接抛异常时，只返回通用错误；
- 结果太大时整次失败。以后有 Artifact 后，可以另行设计“保存大结果，只返回引用”；
- 如果进程在 Tool 运行中退出，F-0006 不猜测 Tool 是否已经完成，也不自动继续。P2 再处理恢复和
  `UNKNOWN`；
- 用户取消或进程中断永远不会被写成成功。

## 10. 安全与隐私

- 模型给出的名称和参数、Tool 返回的数据，都先当作不可信输入检查；
- Tool 自己的说明卡来自程序注册，单次请求不能覆盖；
- 允许名单在程序启动时复制保存。Prompt、Skill、工作区文件和 Tool 返回值都不能修改；
- Policy 只检查整理后的参数，避免“批准一个写法、执行另一个含义”；
- 错误里不放密钥、授权头、原始异常、堆栈或完整敏感输出；
- F-0006 不注册 shell、代码、网络或真实文件 Tool，也不启动宿主机子进程。

## 11. 怎样检查执行过程

调用者可以直接从 `ToolResult` 看出成功还是失败。失败代码能区分名称不存在、参数错误、权限拒绝、
timeout、结果过大和 Tool 异常，不需要解析一段自由文本。

F-0006 还不写 Event。F-0016 接入时必须把请求、Policy 决定、开始和结束写成连续 Event，之后
`inspect/events` 才能还原整段过程。

## 12. 上线与回退

这次代码落地后，CLI 行为不会变化，因为还没有真实文件 Tool，也没有 Agent Loop 调用 Executor。
如果需要回退，可以整体删除新组件并恢复旧测试 Tool；没有数据库或外部数据需要处理。

以后 Tool 数据开始写入 Event 后，再做不兼容修改必须增加版本，不能覆盖旧数据。

## 13. 验收标准

下面八件事全部成立，F-0006 才算完成：

1. 非法名称、未知字段、非 JSON object、过深/过大的数据和非法 timeout 会被拒绝；
2. Registry 拒绝重名，只做精确查找，并以稳定顺序列出 Tool；
3. 正常请求严格按 `prepare -> Policy -> execute` 运行，Tool 只执行一次；
4. 参数错误或权限拒绝时，Tool 没有执行；
5. 模型和 Tool 返回值都不能扩大允许名单，外部写入和代码执行在 P1 始终被拒绝；
6. timeout、Tool 主动失败、异常和超大输出得到不同的安全错误，且不泄漏敏感信息；
7. 调用者取消会原样向上传递，Executor 不会自动重试；
8. 公共 Schema、架构边界、类型检查、全部测试、文档、站点和安装包验证通过。

## 14. 验证方式

- 单元测试检查数据限制、冻结、Registry 和固定 Policy；
- 共用接口测试检查 Fake Tool 的 `prepare`、`execute` 和错误规则；
- 集成测试用内存 Tool 跑完整条路径，不访问真实文件或网络；
- 安全测试检查默认拒绝、未注册名称、权限篡改和敏感信息泄漏；
- timeout 和异常测试确认同一请求不会执行第二次；进程恢复仍留到 P2；
- 本 Feature 没有 Agent Loop 或真实文件任务，因此不做模型效果评测。

## 15. 文档同步

- [x] 更新 Spec、Plan、架构和 ADR 链接；
- [x] 新增一页初学者说明，用一次 Tool 请求解释 `prepare`、Policy 和执行；
- [x] 新增开发者导读，标出代码入口和最重要的测试；
- [x] 更新当前状态，同时写清“还没有真实文件 Tool 和 Agent Loop”；
- [x] 确认没有部署变化；
- [x] 更新公共 Tool/Policy Schema 快照。

## 16. 尚未决定的问题

无。项目所有者于 2026-08-14 接受本 Spec：P1 在程序启动时列出允许的 Tool；没有列出的
一律拒绝；外部写入和代码执行始终拒绝。F-0006 不顺带实现真实文件 Tool、Event v2 或自动重试。
