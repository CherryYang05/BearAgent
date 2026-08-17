---
title: "ADR-0011: Workspace tools accept portable relative paths and never follow links"
status: accepted
date: 2026-08-16
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0011：workspace Tool 只接受可移植相对路径，并且不跟随链接

## 要解决的问题

模型请求读取 `docs/guide.md` 时，权限检查和真实打开必须指向同一个对象。仅检查字符串不包含 `..`
还不够：绝对路径、Windows 盘符或设备名可以改变路径含义，symlink 和 junction 也可以让 workspace
内的名字跳到外部。

三个只读 Tool 如果各自处理路径，会逐渐产生三套规则。把 `Path.resolve()` 的结果检查为“仍在根目录
内”虽然更集中，却会默认跟随链接，并留下“什么时候解析、什么时候打开”的别名和竞态问题。F-0007
必须先决定一条跨平台、个人能够维护的 P1 规则。

## 选择时最看重什么

- 可维护性：三个 Tool 共用一个小边界组件，Runtime 不导入文件系统细节；
- 恢复语义：只读调用失败后不自动重试，不产生需要核对的写入；
- 安全：模型路径不能离开根目录，权限检查和执行使用同一份规范化参数；
- 复杂度/交付时间：只使用 Python 3.12 标准库，不同时维护 POSIX 和 Windows 两套核心接口；
- 兼容与迁移：P1 路径在 Windows 和 POSIX 上有同一文本表示，不保存宿主绝对路径。

## 比较过的方案

### 方案 A：只拒绝绝对路径和 `..`

实现最少，也允许工作区中的所有现有布局。但 symlink、junction、Windows device path 和 alternate
data stream 仍可能改变访问对象。每个 Tool 如果再自行补洞，规则会分叉。这不能作为安全边界。

### 方案 B：解析真实路径，只要结果仍在根目录就允许链接

这种方案可以支持指向 workspace 内部的链接，对一些仓库更方便。代价是同一文件会有多个模型可见
路径；检查时解析到的目标也可能在打开前变化。Python 官方文档明确区分纯路径操作、跟随链接的
`resolve()` 和不跟随链接的 `lstat()`，并提醒目录遍历假设目录没有在过程中被替换。要跨平台收紧
竞态，需要更多 OS 专用目录句柄或文件句柄代码。

### 方案 C：可移植相对路径，所有名称跳转都拒绝

模型路径先按统一语法规范化。执行时再检查每一段真实目录项，不跟随 symlink、junction 或其他名称
跳转；普通文件打开后比较检查前后的文件身份。这会拒绝一些本来指向 workspace 内部的便利链接，
但路径含义单一，三个 Tool 可以复用同一组件。

## 决定

选择方案 C。

1. workspace 根目录由可信启动代码传入。它必须是已经存在的普通目录，自身不能是 symlink 或
   junction；adapter 保存一次规范化根路径，单次 ToolRequest 不能修改它。
2. 模型输入可以使用 `/` 或 `\` 分隔；纯规范化在 Policy 前把两者统一成 `/`，`.` 表示根目录。
   它拒绝绝对路径、盘符、UNC、rooted path、`..`、NUL、控制字符、冒号、尾随点/空格和 Windows
   保留设备名。Unix 中名称本身含 `\` 的文件不开放，以换取跨平台一致含义。
3. 纯规范化发生在 Tool `prepare` 中，不访问文件系统。Policy 因而只看到唯一的相对路径文本。
4. 物理边界检查发生在 workspace adapter 的 `execute` 中。它逐段检查目录项，不跟随 symlink、
   junction 或名称跳转，只接受普通目录和普通文件。
5. 打开文件前保存对象身份；打开后用文件句柄状态再次比较。不同则关闭并拒绝，内容不能被读取。
6. 目录列出和搜索可以返回链接项的相对名称或有限跳过计数，但不能读取目标或返回目标路径。
7. 三个 Tool 共享边界组件，不复制路径规则；`domain`、`ports` 和 `runtime` 不导入该 adapter。
8. F-0007 明确不宣称抵御拥有 workspace 并发写权限的本机攻击者替换任意祖先目录。P3 需要用隔离
   runner、只读挂载和 OS 级边界处理这一威胁，不能把 P1 检查描述成 sandbox。

这个决定只覆盖 P1 内置 workspace Tool。F-0008 写入还必须额外决定临时文件、原子 replace 和输出
目录边界；P3 的 sandbox 也不能直接复用“应用层检查等于隔离”的假设。

## 带来的影响

### 得到的好处

- 模型、Policy 和 Tool 使用同一个规范化相对路径；
- Windows 与 POSIX 的常见绕过写法在文件访问前失败；
- 三个 Tool 的文件系统规则集中，Runtime 继续只认识 BearAgent Tool port；
- 默认不跟随链接，递归搜索不会因链接环路无限遍历；
- 不引入生产依赖，也不启动 shell 或外部搜索进程。

### 接受的代价

- 指向 workspace 内部的 symlink 或 junction 也不可读；
- 不同操作系统可能暴露不同的底层错误，但对外只能映射成稳定、安全的 BearAgent 错误；
- 应用层检查无法替代 P3 隔离挂载；
- 打开前后身份比较和分段遍历增加少量 adapter 代码与安全测试。

## 迁移和回退

F-0007 之前没有真实 workspace Tool 或持久路径数据，因此无需迁移。回退可以删除新增 adapter 和错误
代码；CLI 和 SQLite 不变。

如果未来确实需要读取 workspace 内部链接，必须用新的 ADR 说明允许条件、竞态处理和跨平台行为，
不能只删除一条 `is_symlink()` 检查。

## 怎样验证

- 对同一组路径字符串在 Windows 和 POSIX 规则下做表格化单元测试；
- 在临时 workspace 创建向内/向外 symlink，并在 Windows 支持时创建 junction，确认都不跟随；
- 用测试钩子在“检查完成、打开文件”之间替换目标，确认文件身份不一致时没有读取新内容；
- 目录搜索只进入普通目录，并对链接、特殊文件、过深/过大输入返回有限结果；
- 架构测试确认 `domain`、`ports`、`runtime` 没有导入 `adapters.tools`；
- 在 Windows 和 Ubuntu CI 跑同一组契约、集成和安全测试。

重新评估条件：P1 固定任务必须读取受控的 workspace 内部链接，或 P3 的只读隔离挂载已经能提供比
应用层路径规则更强且跨平台一致的边界。

项目所有者于 2026-08-16 接受本决定，并要求 `/` 与 `\` 输入都兼容；规范化后的权限与执行路径仍只
使用 `/` 这一种文本形式。

## 参考资料

- [Python 3.12 pathlib 文档](https://docs.python.org/3.12/library/pathlib.html)：`resolve()`、`lstat()`、
  `is_symlink()`、`is_junction()` 和目录遍历的链接行为；
- [Python 3.12 os 文档](https://docs.python.org/3.12/library/os.html)：`stat(..., follow_symlinks=False)`、
  `scandir()`、`DirEntry` 和不同平台支持范围。
