---
title: P1 闭环审查与收口记录
status: accepted
---

# P1 是否已经可以闭环

**架构与执行主链具备 P1 的基础；本次发现的默认凭据可读问题修复并交付后，才适合按当前代码重新
确认收口。** P1 的完成线是“有限文件任务可执行，已提交过程和失败可查询”，不是自动恢复，也不是
任意任务必然完成。历史 5/5 gate 保留为当时的证据，不能覆盖后来发现的缺陷。

2026-09-05 从 `de99e78` 开始审查，初始工作树干净。审查沿 CLI/config、bootstrap、AgentLoop、Context、
模型 adapter、Registry/Policy/Executor、workspace 与 SQLite/reducer 跟踪主执行链和失败边界，并检查
对应 contract、integration、security、recovery、evals 与文档入口。原有 Windows 测试为 490 passed。

## 1. 架构判断

| 部分 | 判断 | 原因与后续动作 |
|---|---|---|
| domain / ports / adapters | 保留 | 核心只交换 BearAgent 数据，SDK 留在模型 adapter，架构测试约束依赖 |
| application AgentLoop | 保留串行主链 | 外部调用前后追加 Event，单进程和有限任务可维护；P2 扩展恢复决策时再提取调度职责 |
| Reducer 与预算 | 保留 | 状态由已提交 Event 计算，预算限制下一次 Activity；真实账单和硬中断不能由此推断 |
| SQLite 与 projection | 保留 | append、校验和 projection 同事务；P2 需要从 Event 重建，不能依赖 projection 永不损坏 |
| Tool 执行入口 | 保留，修复文件可见范围 | Policy 默认拒绝没有问题，但允许 read 的 workspace 曾包含 Runtime 自己的凭据 |
| 运行诊断 | 保留 best-effort 固定字段 | 日志不参与状态或恢复；当前关联 ID 和耗时不等于完整因果 trace |
| 框架扩展方式 | 逐个稳定 port | 当前无需 DI container、服务化或多 Agent；先让两个研究策略能在同一实验中替换 |

没有证据支持整体推倒重构。此次只抽出启动和 doctor 共用的本地校验，扩展已有访问 Boundary，新增
离线初始化。Event、SQL、Reducer、Policy 的公开契约不变，也没有新增生产依赖。

## 2. 已发现并处理的问题

### 必须修复：默认配置会被当作输入资料

README 默认 workspace 为仓库根，config 为 `data/config.json`。原实现只防越界和链接，不排除这个
普通文件。在临时目录中放入伪造 API key，read 与递归 search 均返回该值；这条路径还可能进入 Event
和下一次模型请求。没有读取或发送用户实际凭据。

F-0020 在 Boundary 保护默认运行目录和实际自定义文件；遍历跳过，显式访问拒绝；硬链接别名也被拒绝。
测试使用真实 SQLite、Workspace Tools、Policy、AgentLoop 与 Fake Provider，验证秘密不进入 Event
或 Context，而普通输入仍可读。详见 `tests/security/test_runtime_files.py`。

### 应补齐：新用户不应手工拼接默认路径

以前要复制两份模板，再把五个零预算改成可运行值；CLI 手册甚至建议第一次传入全部默认路径。
现在 `init` 只创建缺失文件，生成有限 profile；用户填写 config 后可以用 `doctor --check-config`
离线检查，再直接 `run`。原来的零预算样例保留作故障演练。测试覆盖初始化、重复调用、部分失败、
配置错误与默认路径上的 Run/inspect/events，见 `tests/integration/test_local_setup_cli.py`。

### 必须澄清：账面 0、终态成功与长期研究目标

普通 v2 config 不保存价格，bootstrap 使用 `unpriced`。因此 cost=0 不能表示免费，费用预算也不是
Provider 账单上限。human renderer、README、配置参考和教程已明确这一点。

`RunSucceeded` 表示模型返回有效终态回答，不是答案质量检查。Artifact hash 记录写入时的内容，不是
查询时重新校验文件。README 原来用现在时描述诊断、干预和恢复，已改成明确的未来方向，并区分副作用
核对与因果诊断验证。

## 3. 文档怎样重新组织

保留六部分学习结构，不按 Feature 年表重建教程。主要调整是：

- 第一站改为[第一次运行](../../site/src/content/docs/zh-cn/learn/first-run.md)：看到文件与 Event 后才认识术语；
- CLI 手册保留选项和排错，但正常路径使用默认配置；配置学习页删去用户不需要的 live gate 操作和产品比较；
- 初学者明确知道“本地记录”与“可能调用远程模型”的区别，以及成功状态不代替任务验收；
- 加入[从失败到研究问题](../../site/src/content/docs/zh-cn/learn/research-experiments.md)，把具体故障、假设、
  可推翻的预测、验证动作和指标连接起来；
- 同步 docs 架构、定位、路线、索引，以及站点开发者和状态入口。

叙述顺序参考 [AI Agents in Depth 第 1 章](https://bojieli.github.io/ai-agent-book/book/chapter1/)的具体
例子与配套实验组织方式；没有复制其能力为 BearAgent 当前状态，也不以外部文章代替代码证据。

## 4. P1 缺什么，哪些不必挤进来

配置保护属于必须关闭的安全缺口，初始化与检查补足基本可用性。Session 多轮对话、自动模型发现、
全局配置搜索、进程恢复、Approval、sandbox、Web/MCP 都不是现有 P1 文件任务闭环的必要条件。
`runs list`、更细的配置字段提示、显式价格配置可以作为后续小 Feature，按真实使用反馈安排。

当前仍有明确限制：Context 和查询历史有界，普通搜索不解释 gitignore；模型 API 可能严格拒绝未知流
事件或缺失 usage；墙钟和 token 预算不撤销已开始的调用；强并发本机目录攻击不在文件 Boundary 的
承诺内。部署到网络、作为长期服务或处理高风险操作，要等待对应的恢复与隔离能力。

## 5. P2/P3 的下一步

P2 先从 Event-only 重建与 Attempt 开始，再做可核对写入、`UNKNOWN` 和控制命令。Checkpoint 由实际
重放成本决定，实验清单与策略比较从 P2 开始，不推迟到 P5。P3 再约束诊断干预的权限、预算、扰动
和 runner 资源。科研算法输出提议，不能绕过执行门。

这条路径可以逐步形成框架，但不把“文件任务恢复”包装成“LLM serving 跨层故障定位”。Future 的可读
讨论支持研究动机，最终 RP 附件未由接口提供。详细切片、指标、基线和边界见
[科研 Runtime 规划](research-runtime.md)。

## 6. 本轮验证与交付状态

本地完整测试从基线 490 增至 507 个通过。Ruff、Pyright、schema、151 个 Markdown 链接、governance、
48 页站点构建、sdist/wheel 和独立安装的 wheel CLI 均通过。浏览器实看浅色、深色与 390px 窄屏，
修正了教程标题断行与研究流程图缩小后无法阅读的问题。

线上域名最初因尚未创建独立虚拟主机而出现 TLS `ERR_SSL_UNRECOGNIZED_NAME_ALERT`。项目所有者随后
在 1Panel 创建站点；本轮把 `site/dist/` 改为由 OpenResty 直接提供的静态文件。服务器和公网浏览器
均通过有效 HTTPS 打开首页、新手教程与研究教程，关键资源返回 200。

- 基线：Windows / Python 3.12，490 个测试通过；凭据泄漏用临时伪造文件单独复现。
- 新增回归：默认/自定义保护、硬链接、Event/Context、初始化和默认 CLI 链路。
- 完整质量门与站点阅读检查的最终结果记录在 [PLAN-F-0020](../plans/PLAN-F-0020-safe-local-startup.md)。
- 原 F-0017 的真实 5/5 为历史报告；本轮不读取真实 key，也不产生模型费用。
- 本轮代码和 site 内容仍在本地工作树；没有提交、推送或触发新 CI。文档站已按项目所有者明确授权
  手工部署；这不等于跨平台 CI 通过，也不把 BearAgent Runtime 暴露到公网。

F-0020 的 Spec 保持 accepted、Plan 保持 active，直到按后续发布指令记录不可变的 commit/PR 证据。
本地实现完成与正式 Feature 关闭是两件事；不使用旧提交冒充新实现证据。
