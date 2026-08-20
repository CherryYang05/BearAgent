---
title: F-0008 原子输出与 Artifact 实现导读
description: 找到 workspace.write、同目录暂存、Artifact 契约和故障测试。
bearStatus: implemented
sourceRefs:
  - F-0008
  - PLAN-F-0008
  - ADR-0012
  - F-0006
  - F-0007
---

阅读 F-0008 时，先跟一份内容怎样从 ToolRequest 走到唯一的 `os.replace`，再看 Artifact 字段。
关键不是“调用了文件写 API”，而是任何外部改动都发生在 Policy 之后，目标只在提交点一次改变。

```text
workspace.write.prepare
  -> 纯校验并规范化 outputs 路径和 UTF-8 内容
  -> FixedToolPolicy
  -> ToolExecutor
  -> WorkspaceBoundary.stage_output
  -> 同目录临时文件：write + fsync
  -> 复核 deadline、目录身份和目标类型
  -> WorkspaceBoundary.commit_output：os.replace
  -> ToolResult(Artifact)
```

## 代码地图

| 位置 | 责任 |
|---|---|
| `domain/artifacts.py` | 冻结 Artifact、类型/编码枚举、路径、大小和 SHA-256 约束 |
| `domain/schema.py` | 把 Artifact 加入公共 JSON Schema 快照 |
| `adapters/tools/workspace_limits.py` | 写入内容、单行、输入、结果和 timeout 上限 |
| `adapters/tools/workspace_boundary.py` | 创建安全父目录、同目录暂存、对象身份复核和原子提交 |
| `adapters/tools/workspace_write.py` | ToolSpec、prepare、Artifact 构造和安全失败转换 |
| `adapters/tools/__init__.py` | 保留只读工厂，并让四个 Tool 共用一个 WorkspaceBoundary |

Artifact 属于 `domain`，因此 Runtime、Event 或未来 API 可以使用 BearAgent 自己的类型，不需要导入
文件 adapter。相反，暂存路径和宿主绝对路径只存在于 adapter 内，不能越过 ToolResult 边界。

## prepare 为什么不能创建 outputs

`prepare` 发生在 Policy 之前，只能校验和规范化参数。它检查：

- 路径必须是 `outputs/<file>`，并满足 F-0007 的跨平台相对路径规则；
- 内容必须是 UTF-8 文本，不含 NUL，最多 512 KiB，单行最多 64 KiB；
- 未知字段和错误类型直接拒绝。

目录创建、目标检查和临时文件都在 `execute` 内。这样未 allowlist 或 Policy 拒绝的请求不会留下
`outputs` 目录，也不会让参数校验提前触碰外部环境。

## 提交前为什么要反复核对

`stage_output` 逐层检查或创建普通父目录，拒绝 symlink、junction、reparse point 和特殊对象。临时
文件使用目标目录中的独占名称，按块写入后 flush 并 `fsync`。返回 staged 对象时会保存父目录和
临时文件身份。

`commit_output` 再核对这些身份、目标类型和 deadline，然后同步执行 `os.replace`。同步提交不跨
`await`：如果调用已经 timeout 或取消，就不会把 replace 留给一个仍在后台运行的工作线程。

正常异常路径会尽力删除身份仍匹配的临时文件。强制终止进程仍可能留下残片；F-0008 明确不增加
后台清理器，也不把残片当成已提交结果。

## 成功结果为什么先构造 Artifact

Tool 在暂存前根据规范化路径和内容 bytes 构造 Artifact，并预先确认成功 ToolResult 不超过输出
上限。Artifact 包含新 UUID4、`text`、`utf-8`、字节数和小写 SHA-256，不包含全文或宿主路径。

F-0016 已由 Agent Loop 把 ToolCallId、来源 Activity、规范化请求和包含 Artifact 的完整 ToolResult
保存成 v2 Event；文件 adapter 仍不伪造 Run 身份。SQLite 复用原有 Event JSON 列，没有 migration
或独立 Artifact 查询表。

## 测试从哪里看

- `tests/unit/test_artifacts.py`：字段约束、冻结性和 JSON 往返；
- `tests/unit/test_workspace_write.py`：纯 prepare、创建/替换、内容边界和 Artifact hash；
- `tests/contract/test_workspace_tools.py`：四个 Tool 的可信 ToolSpec；
- `tests/integration/test_workspace_tools.py`：Registry、Policy、Executor 后写入并用 read 读回；
- `tests/security/test_workspace_write.py`：默认拒绝、路径逃逸、链接/特殊目标、对象替换、`fsync`、
  replace、timeout、取消和错误脱敏；
- `tests/contract/test_domain_schemas.py`：公共 Schema 快照。

## 修改时守住六个不变量

1. 只有 `outputs/**` 中的普通文件可以成为目标；
2. prepare 和 Policy 拒绝时没有文件系统改动；
3. 目标只通过一次 `os.replace` 提交，不直接截断；
4. 绝对路径、临时名、原始异常和完整内容不进入 ToolResult；
5. `workspace.write` 保持 `WORKSPACE_WRITE/NOT_SAFE`，Executor 不自动重试；
6. F-0008 不增加 Event、SQLite 状态、delete Tool 或自动清理。

application RunResult 会返回 Artifact 元数据；F-0005 的 CLI 已能启动任务，并由 `run inspect` 从已提交
Tool Event 重建同一组 Artifact。当前仍没有独立 Artifact 数据库或下载 API。
