---
title: "ADR-0012: Commit P1 output files atomically and keep Artifacts user-managed"
status: accepted
date: 2026-08-17
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0012：P1 输出先原子替换，再由用户管理 Artifact 生命周期

## 要解决的问题

模型准备把报告写到 `outputs/intro.md`。如果 adapter 直接打开目标并逐段写入，进程退出或磁盘错误
会把旧结果截断成半份。如果先写系统临时目录再移动，临时文件和目标可能不在同一文件系统，移动会
退化成复制或直接失败。

即使文件完整写入，F-0008 仍要回答：怎样让后续 Event 核对“这次生成了什么”，以及成功结果何时
自动删除。原子提交、Artifact 元数据和保留规则如果不先统一，文件 adapter、Agent Loop、SQLite 和
CLI 会形成不同假设。

## 选择时最看重什么

- 可维护性：只用 Python 3.12 标准库，写入和读取复用同一 workspace 边界；
- 恢复语义：replace 前不改变目标，replace 后用路径和 hash 为 P2 reconcile 留下依据；
- 安全：只允许 `outputs/**`，不跟随链接，不让模型指定临时文件或越界 rename；
- 复杂度/交付时间：P1 不提前实现 Artifact 数据库、自动清理服务或 OS 专用事务层；
- 兼容与迁移：Windows 和 POSIX 使用同一 Tool 契约，不修改 v1 Event 或 SQLite schema。

## 比较过的方案

### 方案 A：直接打开目标并写入

实现最短，但 `open(..., "w")` 会先截断旧目标。编码、timeout、磁盘错误或进程中断都可能留下空文件
或半份结果，不能满足“用户只看到旧结果或完整新结果”。

### 方案 B：写到系统临时目录，再 move/copy 到 outputs

系统临时目录创建方便，但不保证与 workspace 位于同一文件系统。`shutil.move` 可能从 rename 退化成
copy + delete；copy 期间目标可见为半份内容。不同平台的临时文件重开和删除规则也会增加 Windows
特例。

### 方案 C：在目标目录独占创建临时文件，完整落盘后 replace

临时文件与目标位于同一目录。adapter 写完确切 UTF-8 bytes，执行 `flush + os.fsync` 后关闭句柄，
重新检查 deadline 和路径，再同步调用一次 `os.replace`。成功后目标一次切换；replace 前失败时旧目标
不变。代价是需要管理临时文件、父目录和强制退出残留。

## 决定

选择方案 C，并同时确定 P1 Artifact 生命周期：

1. 唯一写入 Tool 是 `workspace.write`。它声明 `WORKSPACE_WRITE` 和 `NOT_SAFE`，只有在固定 allowlist
   中才执行；外部写入和代码执行仍被硬拒绝。
2. 模型只提供 `outputs/<file>` 和有限 UTF-8 `content`。路径在 Policy 前规范化；输出根、临时名称、
   timeout 和上限来自可信代码。
3. `outputs` 或内部父目录缺失时，Tool 可以在 Policy 允许后逐层创建普通目录。已有父段如果是
   symlink、junction、reparse point 或特殊对象，写入失败。
4. 临时文件用标准库安全独占创建方式放在目标目录。adapter 写完全部 bytes，执行
   `flush + os.fsync` 并关闭句柄，再复核父目录、目标类型和 deadline。
5. 最终提交只执行一次同步 `os.replace(temp, target)`，中间不跨 `await`。目标不存在时创建；目标为
   普通文件时替换；链接、目录或特殊对象时拒绝。
6. “原子”只承诺目标可见内容不会是半份。文件 `fsync` 不扩大成断电后目录项一定持久的承诺；P1
   也不宣称 exactly-once。
7. 成功结果返回冻结 `Artifact`：新 ArtifactId、规范化路径、text/UTF-8、size_bytes 和 SHA-256。
   ToolResult 的 ToolCallId 供 F-0016 关联来源 Activity/Run。
8. F-0008 不增加 Event、SQLite migration 或 Artifact store。F-0016 必须用新 Event 版本保存完整
   ToolResult，不能改变已有 v1 Tool Event。
9. 成功 Artifact 在 P1 没有 TTL，不自动删除。用户可以保留或用后续成功写入替换；F-0008 不增加
   delete Tool。
10. 正常失败路径尽力删除临时文件。强制退出可能留下残留；P2 根据请求路径、目标 hash 和临时文件做
    reconcile/清理，P1 不自动扫描。
11. 威胁模型沿用 ADR-0011：应用层复核常见链接和最终对象替换，但不声称抵御能够并发替换任意祖先
    目录的本机攻击者。P3 仍需要隔离挂载和独立 runner。

## 带来的影响

### 得到的好处

- replace 前的可控失败不会截断已有输出；
- 新建和替换使用同一短路径，Windows/POSIX 可运行同一组契约与安全测试；
- Artifact hash 来自将要提交的确切 bytes，Event、inspect 和 P2 reconcile 有稳定依据；
- Tool、Policy 和文件边界保持现有依赖方向，不把 OS 类型带进 Runtime；
- 没有新生产依赖、后台清理服务或数据库 migration。

### 接受的代价

- 创建父目录后、文件提交前失败时，空目录可以保留；
- 强制退出可能留下同目录临时文件，P1 不自动清理；
- replace 成功后、ToolResult 保存前退出时，完整文件可能存在但没有 Event；
- `fsync` 和同目录 replace 比直接 `write_text` 多一些 adapter 与故障注入代码；
- P1 不提供 Artifact 历史查询、TTL、配额回收或删除入口；
- 应用层路径检查仍不是对抗本机攻击者的 sandbox。

## 迁移和回退

F-0008 之前没有写入 Tool、Artifact 类型或持久 Artifact 元数据，因此不需要数据迁移。实现时可以在
BearAgent 仓库 `.gitignore` 中忽略根目录 `outputs/`，避免演示产物误入版本控制；这不改变其他
workspace 的规则。

回退可以删除写入 Tool、Artifact 类型和 Schema。已经生成的 `outputs/**` 属于用户结果，不能由
回退脚本自动删除。若 F-0016 以后已把 Artifact 写入 Event，再回退必须保留历史 Event 兼容代码或
另写兼容性 ADR。

## 怎样验证

- 目标不存在和已存在时核对 bytes、size 和 SHA-256；
- 在临时文件创建后、写入中、`fsync` 后和 replace 处注入失败，确认旧目标不变；
- Windows/Ubuntu 测试绝对路径、`..`、盘符、UNC、symlink、junction、特殊文件和父目录替换；
- 通过 Registry、Policy 和 Executor 运行真实写入，确认未 allowlist 时零文件改动；
- 模拟 timeout/取消，确认不自动重试，replace 前终止不提交目标；
- 校验 Artifact Schema、wheel 导入、pytest、Ruff、Pyright、文档链接和站点构建；
- P2 开始时重新评估目录持久性、临时文件 receipt、reconcile 和自动清理。

## 参考资料

- [Python 3.12 `os` 文档](https://docs.python.org/3.12/library/os.html)：`os.replace`、`os.fsync` 和
  跨平台文件操作语义；
- [Python 3.12 `tempfile` 文档](https://docs.python.org/3.12/library/tempfile.html)：安全临时文件创建和
  Windows 重开/删除限制；
- [ADR-0011](ADR-0011-workspace-relative-paths-no-links.md)：可移植相对路径、链接拒绝和 P1 威胁模型。

项目所有者于 2026-08-17 接受本决定。
