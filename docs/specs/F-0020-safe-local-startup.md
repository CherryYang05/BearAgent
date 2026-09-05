---
title: "Feature: protect local runtime files and simplify first-run setup"
status: accepted
spec_id: F-0020
milestone: P1
change_level: S2
owner: CherryYang05
created: 2026-09-05
last_updated: 2026-09-06
implemented_in: null
related_adrs: [ADR-0011, ADR-0014, ADR-0015, ADR-0018, ADR-0019]
---

# F-0020：初始化一次配置，并把运行资料挡在文件工具之外

## 问题与范围

从 README 在仓库根运行时，workspace 与保存密钥的 `data/` 重叠。2026-09-05 的离线审查在临时
目录放入伪造凭据，确认 `workspace.read` 和 `workspace.search` 都能返回它。490 个原有测试通过，
但没有覆盖这个组合。这违反 F-0017 已有的 Provider 配置不可进入 Tool 输出的要求。

同一次审查发现，首次运行还要复制两份 JSON、手填五个非零预算，CLI 手册又要求显式指定默认路径。
本 Feature 落实本轮项目所有者要求的 P1 修复和简化配置；因跨 bootstrap、文件访问与 CLI 边界，按
S2 记录。它不改变 P2/P3 的状态机，也不提前实现研究算法。

收口期间，项目所有者进一步要求在推送 GitHub 后发布 `site/`。Git 没有可靠的 post-push hook，因此
本 Feature 的交付切片增加 main push 后的受限静态文档 workflow；它不部署 Runtime。

## 用户得到什么

```console
bearagent init
bearagent doctor --check-config
bearagent run "阅读 docs，把简介写到 outputs/intro.md"
```

`init` 只建立缺失的本机模板。用户填写 config 的协议、URL、key 与模型；生成的 profile 已含有限预算。
后续命令继续默认读取当前目录下的 `data/`。现存文件原样保留。初始化与检查均不调用模型。

## 必须满足的行为

1. 文件工具保留根目录下的 `data/`、`.git/` 与 `.env`、`.env.*`；这些不是可交给模型的工作资料。
   bootstrap 另传入实际 config、profile、数据库及 SQLite sidecar 路径，覆盖自定义文件位置。
2. 显式读取、列目录、搜索、写入都遵守同一个 Boundary。遍历遇到受保护条目时标为 blocked 并跳过；
   直接访问返回 `workspace_path_denied`。不读取内容后再做字符串脱敏。
3. 拒绝多硬链接普通文件，避免用另一个文件名读取受保护配置。仍不承诺抵御能够并发改写整个目录树
   的本机攻击者；P3 隔离挂载保留为更强边界。
4. `init` 不覆盖文件，不跟随最终文件或 `data/` 的 link/junction，不接受 key 参数，不打印配置内容。
   key 模板为空，填写前不能开始真实 Run。重复运行只补缺失文件；部分失败不删除已有用户文件。
5. 初始 profile 使用有限的模型次数、Tool 次数、token、单次输出与时间限制。原有零预算示例保留作
   零调用演练，不再作为新用户正常运行的唯一入口。
6. `doctor --check-config` 离线检查 profile、Provider 引用、配置结构、Tool 名单、workspace、非零启动
   预算；检查失败给安全提示，不创建数据库或 Run，不验证服务可达性或某个目标的 Context 容量。
   普通 `doctor` 的环境检查与 JSON 保持兼容。
7. Run help 给出执行选项的发现入口。人类输出解释 cost 是本地账面估算；普通 v2 Run 为 `unpriced`，
   不能从 `cost_microusd=0` 推断免费或有真实账单限额。版本化 JSON 与旧 Event 不变。
8. GitHub 接受 main 推送后重新构建 site，再使用 restricted forced-command key 发布；分支/PR 不部署。
   包校验、大小限制、原子切换、失败回退、host key 固定和公网健康检查必须在自动发布链中完成。

## 架构、安全、迁移与回退

决定见 [ADR-0018](../adr/ADR-0018-runtime-files-outside-workspace-tools.md)。保护路径由可信 composition
构造，模型不能修改。路径和凭据不加入 RunFingerprint；四个文件 Tool 提升 `spec_version` 标记边界变化。
Policy、EventStore、Reducer 的接口和 schema 不变，没有 SQL migration，也不重写旧 Event。

新边界会拒绝以前能读取的受保护资料和硬链接。需要研究的数据应另存为普通输入文件；不可通过关闭
Policy 或移除保护来恢复旧用法。回退 CLI 初始化可保留生成的 config/profile；回退访问保护时必须先把
workspace 与运行资料物理分开。不得删除数据库、凭据或 Artifact。

## 验收与文档影响

- [x] 伪造凭据经过生产 composition 的读、搜索与 Event/Context 回归，均没有内容泄漏。
- [x] 默认路径、自定义配置、SQLite sidecar、路径大小写、分隔符、硬链接与写入保护有回归测试。
- [x] init 重复调用、已有文件、link/junction、部分失败均不覆盖用户资料。
- [x] 配置检查零网络、零数据库；补全配置后可走 Fake production Run、inspect 与 events。
- [x] 完整测试、Ruff、Pyright、schema、governance、docs 链接、站点构建与阅读验证通过。
- [ ] main push workflow、服务器 forced-command key、原子发布与失败回退完成端到端验收。

以上为本地验收，详细命令、507 个测试与环境限制见关联 Plan。尚未记录不可变提交证据，因此 status
保持 accepted，`implemented_in` 保持 null。

| 文档表面 | 更新路径与原因 |
|---|---|
| 权威 docs | `docs/reference/configuration.md`、`docs/architecture/overview.md`、`docs/project/roadmap.md`；修正启动、保护与阶段边界 |
| 初学者 | `site/src/content/docs/zh-cn/learn/first-run.md`、`learn/index.md`、`guides/cli.md`；从第一次操作开始 |
| 开发者 | `site/src/content/docs/zh-cn/development/run-cli.md`、`development/workspace-read-tools.md`；说明 composition 与回归路径 |
| 公开状态 | `README.md`、`site/src/content/docs/zh-cn/project/status.md`、`project/milestones.md`、`site/README.md`；区分历史 gate、本轮验证、线上站点与未实现规划 |

科研方向另见 `docs/project/research-runtime.md`；其接口与算法属于规划，不由本 Feature 授权实现。
