---
title: F-0006 Tool 执行边界实现导读
description: 从请求数据进入 Registry、Policy 和 Executor，并找到对应测试。
bearStatus: implemented
sourceRefs:
  - F-0006
  - PLAN-F-0006
  - ADR-0004
  - ADR-0005
---

F-0006 把原来的 P0 FakeTool 占位升级为一条可复用的执行路径。它不实现真实文件访问，也不写 Event。
阅读代码时，先跟一条请求走完，再看每个类型的细节。

## 请求从哪里经过

```text
ToolExecutor.execute(request)
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

## 修改时先守住三个不变量

第一，`prepare` 必须是纯检查。未来路径规范化可以放这里，实际读取或写入不可以。

第二，Policy 必须看到规范化请求。不要在 Policy 之外复制允许名单，也不要让 Tool 参数覆盖
`ToolSpec` 的副作用类别。

第三，所有执行都经过 `ToolExecutor`。具体 Tool 不应由 Agent Loop 或 adapter 直接调用，否则 timeout、
输出上限和默认拒绝会出现旁路。

## 测试从哪里看

- `tests/unit/test_tool_contracts.py`：JSON 边界、深层不可修改和成功/失败结果规则；
- `tests/unit/test_tool_registry.py`：重名、稳定顺序和精确查找；
- `tests/security/test_tool_policy.py`：默认拒绝、允许名单快照和危险副作用；
- `tests/contract/test_tool_contract.py`：FakeTool 的 prepare/execute 共用接口；
- `tests/integration/test_tool_executor.py`：完整顺序和正常失败；
- `tests/security/test_tool_executor.py`：timeout、取消、异常、超大输出和敏感信息。

F-0007 接入第一个真实 Tool 时，应让同一组接口和 Executor 测试继续成立。F-0016 接线时，只调用
`ToolExecutor.execute`，并负责把前后状态写成 Tool Activity Event。
