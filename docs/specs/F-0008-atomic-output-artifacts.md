---
title: "Feature: Atomic output writing and Artifact metadata"
status: implemented
spec_id: F-0008
milestone: P1
owner: CherryYang05
created: 2026-08-17
last_updated: 2026-08-27
implemented_in: "PR #11"
related_adrs:
  - ADR-0004
  - ADR-0005
  - ADR-0007
  - ADR-0011
  - ADR-0012
---

# F-0008：只把完整结果写进 outputs，并返回可核对的 Artifact

## 1. 为什么现在要做

用户希望 BearAgent “阅读 `docs/`，把介绍写到 `outputs/intro.md`”。F-0007 已经能安全读取
workspace，F-0006 也规定所有 Tool 都经过 Registry、`prepare`、Policy 和 Executor，但仓库仍没有
真正写文件的 Tool。

直接用 `open(path, "w")` 写目标会先截断原文件。进程中途退出时，用户可能只得到半份报告。即使
写入成功，调用者目前也拿不到稳定 ID、内容 hash 和大小，后续 Event 无法说明某次 Activity 具体
生成了哪个结果。

F-0008 只补上这段边界：把有限 UTF-8 文本原子提交到 `outputs/**`，并返回一个可检查的 Artifact。
Agent Loop、Event 持久化和 CLI 仍由 F-0016、F-0005 接通。

## 2. 本次交付

- `workspace.write`：只创建或替换 `outputs/**` 中的 UTF-8 文本文件；
- 与 F-0007 一致的可移植相对路径和真实文件边界，不跟随 symlink、junction 或特殊文件；
- 同目录临时文件加一次原子 replace。提交前失败时，不截断或改写已有目标；
- 冻结的 `Artifact` 类型，包含 ID、规范化路径、类型、编码、字节数和 SHA-256；
- 创建、替换、故障注入、timeout、取消、资源限制和路径逃逸测试；
- 工程文档、初学者路径、开发者入口和当前状态同步。

## 3. 本次不做

- 不接模型、ContextBuilder、Agent Loop、EventStore、SQLite 或 CLI；
- 不保存 Artifact 元数据，不增加 Event schema、SQLite migration 或 Artifact 查询接口；
- 不支持二进制、append、局部 patch、rename、delete、多文件 transaction 或目录 Artifact；
- 不写 `outputs/**` 以外的文件，也不修改已有源码或输入文件；
- 不自动重试，不增加 Attempt、Receipt、Checkpoint 或 `UNKNOWN`；
- 不承诺断电后的目录项持久性，也不实现重启后的临时文件 reconcile；
- 不自动删除成功 Artifact。P1 由用户决定保留或替换，P2 再处理崩溃残留和恢复；
- 不把应用层路径检查描述成 sandbox。并发替换任意祖先目录的本机攻击者仍属于 P3 范围。

## 4. 需要先说明的约定

这里的“原子写”只回答一个问题：其他读取者不会看到半份目标文件。目标在提交前保持旧内容或不存在；
`os.replace` 成功后才一次切换到完整新内容。

它不等于“断电后一定还在”，也不等于“Runtime 一定收到了成功结果”。如果进程恰好在 replace 成功
后、返回 `ToolResult` 前退出，文件可能已存在，但 P1 不会猜测 Run 已成功，也不会自动重试。P2 才
根据目标路径和内容 hash 做 reconcile。

`Artifact` 是 Run 生成、以后可由用户取回的结果。F-0008 先用下面的元数据描述它：

```text
ArtifactId + outputs 相对路径 + text/utf-8 + size_bytes + sha256
```

ToolResult 外层已有 `ToolCallId`。F-0016 后续用它关联来源 Activity 和 Run，再把 Artifact 写进
Event；文件 adapter 不自行伪造 Run 或 Activity 身份。

## 5. 使用场景

### 第一次生成报告

```json
{"path": "outputs/intro.md", "content": "# BearAgent\n..."}
```

`prepare` 先规范化路径并检查内容大小。Policy 允许明确配置的 `workspace.write` 后，Tool 才创建缺失
的 `outputs` 目录、暂存完整内容并提交目标。成功结果返回：

```json
{
  "artifact": {
    "artifact_id": "<uuid4>",
    "path": "outputs/intro.md",
    "kind": "text",
    "encoding": "utf-8",
    "size_bytes": 123,
    "sha256": "<64 lowercase hex>"
  }
}
```

### 替换已有输出

目标已存在且是普通文件时，Tool 先在同一目录写完整临时文件。replace 前发生可控失败，旧文件保持
不变；replace 成功后，新打开的读取者只看到完整新内容。每次成功写入都产生新的 ArtifactId。

### 模型试图写到其他位置

`README.md`、`src/main.py`、`../secret.txt`、绝对路径、盘符、UNC、`outputs` 目录本身、经过
symlink/junction 的路径和特殊文件都被拒绝。Tool 不尝试改成“最接近”的可用路径。

### 暂存完成但提交失败

测试在临时文件写完后注入 replace 失败。调用者得到有限安全错误，旧目标不变。临时文件在正常异常
路径尽力删除；强制结束进程仍可能留下临时文件，P1 不自动扫描或删除。

## 6. 必须满足的行为

### 6.1 模型只能描述一个有限文本输出

- Tool 名称固定为 `workspace.write`，`ToolSpec.side_effect` 是 `WORKSPACE_WRITE`，
  `retry_safety` 是 `NOT_SAFE`；
- 输入只有 `path` 和 `content`，拒绝未知字段；
- `path` 使用 F-0007 的可移植规则，Policy 前统一成 `/`，且必须是 `outputs/<file>`；
- UTF-8 内容最多 512 KiB，不允许 NUL，单行最多 64 KiB。按 UTF-8 bytes 原样保存，不改变换行，
  也不自动补结尾换行；
- 模型参数不能改变 workspace 根、输出前缀、timeout 或可信上限；
- 路径或内容在 `prepare` 失败时，Policy 和文件系统都不运行。

### 6.2 目标文件只在最后一步改变

```text
校验并规范化 path/content
  -> Policy ALLOW
  -> 在 outputs 内创建并复核缺失的普通父目录
  -> 在目标目录独占创建临时文件
  -> 写完全部 bytes，flush + fsync，再关闭句柄
  -> 重新检查 deadline、父目录和目标类型
  -> 同步执行一次 os.replace(temp, target)
  -> 返回已经构造好的 Artifact
```

- 临时文件必须与目标位于同一目录，不能依赖系统临时目录或跨文件系统 move；
- 临时名称由可信代码随机生成，模型不能指定；
- 已有目标只能是普通文件；链接、目录和特殊对象一律拒绝；
- replace 之前不能直接打开目标做 truncate/write；
- 最终 replace 在 async 方法中不跨新的 `await`，并在 replace 前再次检查 Tool deadline；
- replace 成功代表目标在该时刻指向完整新文件，不扩大成断电持久性承诺；
- 失败时尽力删除本次临时文件。已创建的空父目录可以保留，但不能留下半份目标文件；
- 威胁模型与 ADR-0011 一致：复核根目录和父目录，但不宣称抵御拥有 workspace 并发写权限的本机
  攻击者。

### 6.3 成功结果能核对具体内容

新增冻结的 `Artifact` BearAgent 类型：

| 字段 | 含义 |
|---|---|
| `artifact_id` | 本次成功写入的新 UUID4 ArtifactId |
| `path` | 规范化 `outputs/**` 相对路径 |
| `kind` | P1 固定为 `text` |
| `encoding` | P1 固定为 `utf-8` |
| `size_bytes` | 实际提交的 UTF-8 bytes 数量 |
| `sha256` | 实际提交 bytes 的小写 SHA-256 |

- hash 由将要写入的确切 bytes 计算，不能来自模型参数；
- 成功 `ToolResult.data` 只返回 `{"artifact": <Artifact>}`，不重复返回全文；
- `Artifact.path` 是有限元数据，不是重新打开文件的权限；真实访问仍要经过 workspace boundary；
- `Artifact` 和新增枚举进入公共 JSON Schema；
- F-0008 不保存 Artifact。F-0016 必须把 ToolResult 与来源 Activity/Run 写入新 Event 版本，不能
  修改已有 v1 Tool Event 的含义。

## 7. 对外入口和模块连接

| 位置 | 负责什么 |
|---|---|
| `domain.artifacts` | `Artifact`、类型、编码、hash 和大小约束 |
| `domain.schema` | 发布 Artifact JSON Schema |
| `adapters.tools.workspace_boundary` | 复用相对路径规则，增加只允许 outputs 的写入边界 |
| `adapters.tools.workspace_write` | 输入模型、暂存、fsync、replace 和 Artifact 结果 |
| `adapters.tools` | 导出写入 Tool，并提供共享同一 boundary 的四 Tool 工厂 |
| `runtime.policy` | 逻辑不扩权；已有 Policy 只允许 allowlist 中的 `WORKSPACE_WRITE` |

真实调用仍是：

```text
ToolRequest -> ToolRegistry -> workspace.write.prepare
            -> FixedToolPolicy -> ToolExecutor -> workspace.write.execute
```

本 Feature 不增加 CLI/API，不修改 `bootstrap.py` 默认路径，也不让模型直接调用 adapter。

## 8. 状态和保存的数据

成功后，目标文件保存在调用者 workspace 的 `outputs/**`。如果 `outputs` 或内部父目录不存在，Tool
可以在 Policy 允许后逐层创建普通目录；它不创建 workspace 以外的目录。

F-0008 不增加数据库状态、Event 或 migration。Artifact 元数据只存在于本次 `ToolResult`，当前还
不能通过 `run inspect` 查询。这个限制必须继续显示在工程文档和站点状态页。

P1 不设置成功 Artifact 的 TTL，也不自动清理。用户可以让后续成功写入替换同一路径，或在
BearAgent 之外显式管理文件。F-0008 不增加 delete Tool。

## 9. 失败时会发生什么

- 参数、路径或内容错误发生在 `prepare`，不会触碰文件系统；
- Policy 拒绝时不会创建 `outputs`、父目录或临时文件；
- 创建目录、暂存、`fsync` 或 replace 失败时返回有限错误，原目标保持旧内容；空目录可以保留；
- Executor timeout 或调用者取消时不自动重试。暂存在线程中运行时，取消可能留下临时文件，但最终
  replace 只在暂存完成、deadline 未过期且调用继续时同步执行；
- 进程在 replace 前退出时，目标保持旧内容或不存在，临时文件可能残留；
- 进程在 replace 后、结果保存前退出时，完整目标可能存在但没有 Event。P1 不把 Run 标成成功，也
  不自动重写；P2 根据请求路径和 hash reconcile；
- 文件 `fsync` 不承诺断电后目录项一定持久，也不声称 exactly-once；
- 错误不包含绝对路径、临时名、原始异常、堆栈、秘密或完整内容。

## 10. 安全与隐私

- workspace 根由可信启动代码注入，单次请求不能修改；
- 所有写入经过 Registry、`prepare`、固定 Policy 和 Executor；
- `workspace.write` 未进入 allowlist 时默认拒绝；外部写入和代码执行仍被硬拒绝；
- `outputs/**` 的每段真实父路径都拒绝 symlink、junction、reparse 跳转和特殊对象；
- 临时文件在目标目录独占创建，目标只通过一次 replace 改变，不能越界 rename；
- 模型、Prompt、Skill、workspace 内容和 ToolResult 不能扩大输出范围或上限；
- 待写内容仍是不可信文本。保存 Prompt injection 不会改变 Policy，也不会执行其中命令；
- ToolResult 和普通日志只记录 Artifact 元数据，不复制全文。密钥不应进入 Prompt 或 Artifact；
- P1 边界适用于单用户、单进程和受控 workspace，不替代 P3 sandbox。

## 11. 怎样检查执行过程

调用者从 `ToolResult` 可以看到规范化路径、ArtifactId、类型、编码、大小和 SHA-256；失败时看到稳定
ErrorCode。它看不到宿主绝对路径、临时名称或原始操作系统错误。

F-0008 不写 Event。F-0016 接入后，规范化参数、成功 Artifact 或安全失败必须进入 Tool Activity
Event；日志不能复制完整内容。F-0005 后续用同一事实实现 `run inspect/events`。

## 12. 上线与回退

没有数据库 migration 或默认 CLI 变化。写入 Tool 只在可信构造代码显式注册并加入 allowlist 后
可用；只读 Tool 的现有构造入口继续保留。

回退时删除 Artifact 类型、写入 adapter、四 Tool 工厂和新增 Schema。已经生成的 `outputs/**` 属于
用户结果，不自动删除；因为 F-0008 尚未持久化 Artifact 元数据，没有数据库回退步骤。

## 13. 验收标准

1. `workspace.write` 能创建缺失的 outputs/父目录，原子创建或替换 UTF-8 普通文件；成功结果的路径、
   字节数和 SHA-256 与磁盘 bytes 一致；
2. Artifact 使用新 UUID4 ID，类型为 text、编码为 UTF-8，并进入公共 Schema；结果不重复全文；
3. prepare/Policy/暂存/fsync/replace 失败都不留下半份目标；replace 前故障保持旧内容，正常异常路径
   尽力删除临时文件；
4. `outputs/**` 外路径、绝对路径、`..`、盘符、UNC、links、junction、特殊文件和越界 rename 都在
   写外部内容前被拒绝；错误不泄露绝对路径、临时名或原始异常；
5. 内容、单行、路径、输入/结果 JSON 和 timeout 上限不能被模型扩大；超限请求不写文件；
6. 写入经过 Registry、FixedToolPolicy 和 ToolExecutor；未 allowlist 时零文件改动，Tool 标为
   `WORKSPACE_WRITE/NOT_SAFE`，timeout 和取消不自动重试；
7. 故障注入覆盖暂存后失败、replace 失败、目标类型变化和父目录替换；Windows 与 Ubuntu 运行同一
   组单元、契约、集成和安全测试；
8. 不增加生产依赖、Event、SQLite migration、shell、网络或自动清理；工程文档、站点、公共 Schema、
   类型检查、完整测试和安装包验证通过。

## 14. 验证方式

- Unit：Artifact 约束、路径/内容模型、UTF-8 bytes、hash、目录创建、临时文件和 replace；
- Contract：`workspace.write` 满足 Tool 契约，Artifact 公共 Schema 更新；
- Integration：四个 workspace Tool 共享 boundary，并经 Registry、Policy 和 Executor 创建/替换文件；
- Recovery：replace 前注入失败证明目标不变；replace 后中断的 reconcile 留到 P2；
- Security：路径变体、links、特殊文件、目标/父目录替换、权限失败、超大内容、取消、timeout、Prompt
  提权和错误脱敏；
- Eval/manual：不做模型效果评测；手工写 `outputs/intro.md`，再用 `workspace.read` 读回并核对 hash。

## 15. 文档同步

- [x] Engineering source of truth：Spec、Plan、ADR、Architecture、Roadmap、Schema；
- [x] Site beginner learning path：从“为什么不能直接 open 目标”解释暂存和原子提交；
- [x] Site developer documentation：Artifact 契约、写入边界、故障窗口和重点测试；
- [x] Site current status：明确仍没有 Agent Loop、Event 接线或 CLI Run；
- [x] Deployment docs：确认 P1 无部署变化，成功 Artifact 不自动清理；
- [x] Generated reference：Artifact 和 Tool Schema 快照。

## 16. 已确认的决定

1. 首个写入 Tool 命名为 `workspace.write`，只写 UTF-8 文本，内容上限 512 KiB、单行 64 KiB；
2. Tool 可以在 Policy 允许后创建缺失的 `outputs` 和内部普通父目录，也可替换已有普通文件；
3. Artifact 先包含 ID、路径、text/UTF-8、大小和 SHA-256；F-0016 再关联并保存 Run/Activity；
4. “原子”只承诺目标不会出现半份内容，不承诺断电持久、自动恢复或 exactly-once；
5. P1 不自动删除成功 Artifact，也不扫描强制退出留下的临时文件；P2 再做 reconcile 和清理。

项目所有者于 2026-08-17 接受本 Spec 和以上五项决定。
