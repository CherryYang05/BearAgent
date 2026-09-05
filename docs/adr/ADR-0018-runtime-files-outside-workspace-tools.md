---
title: "ADR-0018: runtime files are excluded at the workspace access boundary"
status: accepted
date: 2026-09-05
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0018：文件工具在打开内容之前排除 Runtime 的配置和记录

## 当前冲突

P1 默认以当前目录为 workspace，又把凭据和 SQLite 放在当前目录的 `data/`。`.gitignore` 只限制 Git
跟踪，不会阻止 Python 读取。SecretStr 只能遮蔽已经解析的配置对象，无法保护 `workspace.read` 返回的
原始 JSON。仅写 Prompt 禁令也不能满足 ADR-0015 的密钥边界。

## 决定

保留默认目录，扩展现有 WorkspaceBoundary 的访问检查，修复已接受的秘密保护要求：

- 根目录的 `data/`、`.git/`、`.env` 与 `.env.*` 保留给运行记录、版本管理和本机配置。
- bootstrap 把实际配置、profile、数据库和 `-wal`、`-shm`、`-journal` 路径交给同一个 Boundary。
  不把这些路径放进 Provider schema、Event 或日志。
- 目录遍历在递归前识别 blocked 条目；显式访问与写入目标检查使用同一规则。
- 普通文件有多个硬链接时拒绝读取和作为输出目标，防止使用别名跨过路径保护。
- 初始化是用户 CLI 的本机配置动作，属于可信入口；Agent 提出的写操作仍走 Policy/Executor。
  CLI 不在 Runtime 中新增宿主 shell，也不引入新依赖。

四个 workspace Tool 的 `spec_version` 变成 `2`。这标记声明契约变化，不宣称 fingerprint 包含完整环境
或可重现全部文件。旧 Run 和旧 schema 仍可查询。

## 为什么这样选

把默认 workspace 改成另一个目录可以物理分离，却会让 README 的仓库任务和既有配置换路径。
只禁止 `data/config.json` 会漏掉自定义 config 与数据库；只在 read 中禁止又会漏掉递归搜索。
访问 Boundary 已负责真实路径、链接和文件身份，放在这里可以统一覆盖所有内置文件工具。

这不是任意秘密发现器。用户手工复制到普通资料中的敏感内容仍可能成为 Tool 结果；不承诺抵御恶意
本机进程不断替换目录。P3 应通过隔离 workspace 和不挂载 Runtime secret 进一步缩小可见范围。

## 故障、回退与证据

保护检查失败返回安全的 `workspace_path_denied`，不附加真实路径。目录列表使用已有 blocked 表达，
不新增 Event 或数据库状态。配置初始化失败不覆盖、删除已有文件，重试只补缺失文件。

无需 SQL 或旧 Event 迁移。停用初始化不影响既有配置。回退访问保护前，必须把工作资料和运行资料
放在互不包含的目录，不能重新暴露默认凭据。测试只使用临时目录与伪造密钥，覆盖直接读、递归搜索、
硬链接、SQLite sidecar、自定义位置和 Event/Context 中没有伪造密钥。
