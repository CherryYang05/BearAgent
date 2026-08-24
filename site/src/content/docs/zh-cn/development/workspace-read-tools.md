---
title: F-0007 workspace 只读 Tool 实现导读
description: 找到跨平台路径边界、三个 Tool、资源限制和安全测试。
bearStatus: implemented
sourceRefs:
  - F-0007
  - PLAN-F-0007
  - ADR-0011
  - F-0006
---

阅读 F-0007 时，先跟 `docs\guide.md` 怎样变成 `docs/guide.md`，再看真实文件怎样打开。不要从三个
Tool 的输出字段开始背。

```text
Tool.prepare(raw arguments)
  -> normalize_workspace_path
  -> PreparedToolRequest 使用 /
  -> FixedToolPolicy
  -> ToolExecutor
  -> WorkspaceBoundary 检查真实目录项
  -> list / read / search 返回 ToolResult
```

## 代码地图

| 位置 | 责任 |
|---|---|
| `adapters/tools/workspace_limits.py` | 集中保存路径、目录、文本、搜索、结果和 timeout 上限 |
| `adapters/tools/workspace_boundary.py` | 规范化路径、固定根目录、拒绝链接、核对打开对象 |
| `adapters/tools/workspace_text.py` | 在 byte、line 和 deadline 上限内严格解码 UTF-8 |
| `adapters/tools/workspace_list.py` | 一层目录和 offset 分页 |
| `adapters/tools/workspace_read.py` | 完整行分页和 `next_start_line` |
| `adapters/tools/workspace_search.py` | 按路径稳定排序的普通字符串递归搜索 |
| `adapters/tools/__init__.py` | 保留三个只读 Tool 工厂，并围绕同一个 boundary 构造四个 workspace Tool |
| `domain/errors.py` | workspace 稳定 ErrorCode |

三个 Tool 共享 boundary 和结果辅助函数，但互不调用。`domain`、`ports` 和 `runtime` 也不导入这些
adapter。F-0016 把工厂结果注册到 `ToolRegistry` 后，Agent Loop 不需要了解文件系统细节。

## 两次检查不能合并

`prepare` 中的 `normalize_workspace_path` 必须是纯函数。它接受 `/` 和 `\`，统一成 `/`，并拒绝盘符、
UNC、rooted path、`..`、控制字符、尾随点/空格和 Windows 设备名。这里不能调用 `exists()` 或
`resolve()`，否则 Policy 之前就已经访问了外部环境。

`WorkspaceBoundary` 在执行阶段再检查真实对象。它使用 `stat(..., follow_symlinks=False)` 逐段拒绝
symlink、junction 和 reparse point。普通文件打开后，会把句柄的身份与打开前的对象比较；不一致时
在读取任何内容前失败。

## 资源上限集中在哪里

首个实现的重要硬上限是：

| 范围 | 上限 |
|---|---|
| 路径 | 1,024 bytes、64 段、每段 255 bytes |
| 目录 | 5,000 项；单页 200 项 |
| 文本 | 文件 4 MiB、单行 64 KiB、单页文本 256 KiB |
| 搜索 | 深度 32、文件 2,000、总读取 16 MiB、结果 100 |
| ToolResult | 512 KiB |
| timeout | list 3 秒、read 5 秒、search 10 秒 |

调用参数只能缩小页数或结果数。结果达到可分页上限时返回 `truncated`；目标本身过大、不是 UTF-8 或
访问不安全时返回失败，不能把半截内容伪装成完整结果。

同步文件读取通过 `asyncio.to_thread` 离开 Runtime event loop。调用者取消时取消信号仍向上传播；
工作线程不能被 Python 强行停止，因此文件读取本身也按行检查 deadline 和字节上限。

## 测试从哪里看

- `tests/unit/test_workspace_paths.py`：Windows/Unix 分隔符和拒绝矩阵；
- `tests/unit/test_workspace_boundary.py`：普通文件、目录、类型和安全错误；
- `tests/unit/test_workspace_list.py`、`test_workspace_read.py`、`test_workspace_search.py`：三个 Tool 的
  可观察行为；
- `tests/contract/test_workspace_tools.py`：ToolSpec 和 prepare/execute 契约；
- `tests/integration/test_workspace_tools.py`：真实 Tool 经过 Registry、Policy 和 Executor；
- `tests/security/test_workspace_tools.py`：路径逃逸、symlink、junction、对象替换、文件上限和取消。

Windows 普通用户可能没有创建 symlink 的权限，因此该项会在本机跳过，并在支持 symlink 的 Ubuntu CI
运行。junction 分类和拒绝不依赖管理员权限，另有独立测试。

## 修改时守住四个不变量

1. Policy 只看使用 `/` 的规范化路径；
2. 宿主绝对路径、链接目标和原始异常不进入 ToolResult；
3. 三个 Tool 共用 boundary，不把文件系统检查复制到各自模块；
4. Agent Loop 只能调用 `ToolExecutor`，不能直接调用具体 adapter。

F-0007 仍只负责读取，不写 Event，也不修改 SQLite。F-0008 的写入实现复用同一 boundary，但保持在
独立模块；详见[原子输出与 Artifact 实现导读](/BearAgent/zh-cn/development/atomic-output-artifacts/)。F-0016 负责 Agent Loop 和
Event 接线。
