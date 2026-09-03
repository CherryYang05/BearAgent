---
title: F-0006 Tool 执行边界实现导读
description: 从请求数据进入 Registry、Policy 和 Executor，并找到对应测试。
bearStatus: implemented
sourceRefs:
  - F-0006
  - PLAN-F-0006
  - F-0016
  - F-0018
  - ADR-0004
  - ADR-0005
  - ADR-0016
---

F-0006 把原来的 P0 FakeTool 占位升级为一条可复用的执行路径。它不实现真实文件访问，也不写 Event。
阅读代码时，先跟一条请求走完，再看每个类型的细节。

## 请求从哪里经过

```text
ToolExecutor.execute_recorded(request)
  -> ToolRegistry.get(name)
  -> Tool.prepare(request)
  -> ToolPolicy.evaluate(spec, prepared_request)
  -> Tool.execute(prepared_request)
  -> ToolResult
```

前面任一步失败，后面的步骤都不会运行。`tests/integration/test_tool_executor.py` 用会记录调用次数的
FakeTool 检查了这个顺序。

## 代码地图

| 位置 | 责任 |
|---|---|
| `src/bearagent/domain/tools.py` | ToolSpec、请求、结果、Policy 决定和输入/输出资源上限 |
| `src/bearagent/ports/tools.py` | 具体 Tool 必须实现的 prepare/execute 接口 |
| `src/bearagent/ports/policy.py` | Policy 接口 |
| `src/bearagent/runtime/tool_registry.py` | Tool 快照、稳定排序和精确查找 |
| `src/bearagent/runtime/policy.py` | P1 默认拒绝和危险副作用硬拒绝 |
| `src/bearagent/runtime/tool_executor.py` | 调用顺序、timeout、取消、输出上限和错误转换 |
| `src/bearagent/adapters/testing/tools.py` | 不访问外部环境的确定性 FakeTool |

Registry 构造时只读取每个 Tool 的一次 `ToolSpec`，再把这份冻结值同时用于精确名称索引、稳定排序、
Provider schema、Policy 和 Run fingerprint。这样即使 adapter 把 `spec` 写成动态属性，也不能让查找名称
和真正受检查、被哈希的 contract 分叉。

## 修改时先守住四个不变量

第一，`prepare` 必须是纯检查。未来路径规范化可以放这里，实际读取或写入不可以。

第二，Policy 必须看到规范化请求。不要在 Policy 之外复制允许名单，也不要让 Tool 参数覆盖
`ToolSpec` 的副作用类别。

第三，所有执行都经过 `ToolExecutor`。具体 Tool 不应由 Agent Loop 或 adapter 直接调用，否则 timeout、
输出上限和默认拒绝会出现旁路。

第四，Registry 的注册快照只能读取一次 `ToolSpec`。后续执行和 fingerprint 必须共享这份值，不能再次
向 Tool 查询一份可能不同的声明。

## 测试从哪里看

- `tests/unit/test_tool_contracts.py`：JSON 边界、深层不可修改和成功/失败结果规则；
- `tests/unit/test_tool_registry.py`：重名、稳定顺序和精确查找；
- `tests/security/test_tool_policy.py`：默认拒绝、允许名单快照和危险副作用；
- `tests/contract/test_tool_contract.py`：FakeTool 的 prepare/execute 共用接口；
- `tests/integration/test_tool_executor.py`：完整顺序和正常失败；
- `tests/security/test_tool_executor.py`：timeout、取消、异常、超大输出和敏感信息。

F-0007 的三个只读 Tool 和 F-0008 的原子写入 Tool 已运行同一条 Executor 路径。具体路径检查见
[F-0007 workspace 只读 Tool 实现导读](/zh-cn/development/workspace-read-tools/)，提交点和 Artifact 见
[F-0008 原子输出与 Artifact 实现导读](/zh-cn/development/atomic-output-artifacts/)。F-0016 接线后，
AgentLoop 调用 `ToolExecutor.execute_recorded`，把原始/规范化请求、Policy 决定、adapter 到达标志和结果
写入 Tool Activity Event；旧的 `execute` 仍复用同一私有执行路径，只返回其中的 `ToolResult`。
