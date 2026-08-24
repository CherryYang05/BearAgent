---
title: "Implementation Plan: Starlight documentation site and GitHub Pages publication"
status: active
plan_id: PLAN-F-0015
related_spec: F-0015
created: 2026-08-10
last_updated: 2026-08-25
---

# PLAN-F-0015：Starlight 文档站与 GitHub Pages 发布

关联 Spec：`docs/specs/F-0015-local-starlight-docs-site.md`

## 开始前确认

F-0015 与 ADR-0008 已接受；中文优先、工程事实和公共解释分开维护已经确认。最初的本地站点已经
完成，2026-08-16 又确认把静态站点发布到 GitHub Pages，不发布 Runtime 服务。

## 实施步骤

### 第 1 步：明确工程文档和公共站点的分工

- 状态：completed；
- 交付结果：`docs/` 保存精确事实，`site/` 按读者任务解释，不建立第二套 Feature 状态；
- 代码落点：F-0015 Spec、ADR、Plan、Roadmap 和仓库规则；
- 接入关系：每个站点页面通过状态和来源回到工程事实；
- 重点测试：工程 Markdown 链接；
- 验证：`uv run python scripts/check_docs.py`；
- 回退：删除新增治理说明和索引登记，不影响 Runtime。

### 第 2 步：建立可重复的本地构建

- 状态：completed；
- 交付结果：Starlight、中文路由、Pagefind、Mermaid 和 npm scripts；
- 代码落点：`site/`、package lock 和 CI；
- 接入关系：普通 CI 只安装并构建静态页面，不部署、不读取 Runtime 数据；发布由第 5 步的独立
  workflow 负责；
- 重点测试：锁定安装、生产构建和静态输出；
- 验证：`npm --prefix=site ci`、`npm run build --prefix=site`；
- 回退：删除 `site/`，不影响 Python 依赖和数据。

### 第 3 步：用一次任务组织学习与架构内容

- 状态：completed；
- 交付结果：首页、学习路径、Agent 基础、Runtime 架构、F-0001/F-0002 导读和当前状态；
- 代码落点：`site/src/content/docs/zh-cn/`；
- 接入关系：学习页先讲具体行为，架构页解释 port/adapter，开发者页连接代码与测试；
- 重点测试：站点构建、路由和人工连续阅读；
- 验证：`npm run build --prefix=site`；
- 回退：保留站点骨架，逐页恢复内容。

### 第 4 步：把文档同步和写作质量加入完成标准

- 状态：completed；
- 交付结果：每个 Feature 同步工程事实、学习页、开发者页和状态；禁止机械术语替换；
- 代码落点：`AGENTS.md`、SOP、Spec/Plan/ADR 模板、PR 模板和站点开发者页；
- 接入关系：后续 Feature 先通过代码/测试确认事实，再按页面职责写入不同入口；
- 重点测试：链接、站点构建、变更段落连续阅读和完整工程回归；
- 验证：最终验证命令；
- 回退：回退文档治理，不影响 Runtime 数据和接口。

### 第 5 步：让同一份静态站点可以在线访问

- 状态：in_progress；
- 已完成：Astro 配置公开地址和 `/BearAgent` 基础路径，根页跳转和 404 页面使用相同前缀；
- 已完成：新增只在 `main` 或手动触发的 GitHub Pages workflow；
- 已完成：文档检查在遍历前排除 `.venv` 等目录，并加入回归测试；
- 待完成：合并后在仓库 Pages 设置中选择 GitHub Actions，并检查公开 URL；
- 2026-08-25 复核：仓库 Pages API 与公开项目地址均返回 404，不能把静态构建写成已经上线；
- 代码落点：`site/astro.config.mjs`、`site/src/pages/index.astro`、`site/src/content/docs/404.md`、
  `.github/workflows/deploy-docs.yml` 和 `scripts/check_docs.py`；
- 验证：生产构建、sitemap、根页链接、404 页面、Python 回归测试和首次 Pages deployment；
- 回退：禁用或删除 Pages workflow，保留本地站点，不影响 Runtime。

### 第 6 步：重组 P1 阅读路径并独立维护 CLI 手册

- 状态：completed（2026-08-23）；
- 交付结果：首页先把读者带到 CLI 和当前状态；学习路径按“角色分工 → 完整 Run → 状态与边界”
  逐步深入；新增独立 CLI 手册与 P1 架构取舍页；
- 代码落点：`site/astro.config.mjs`、首页、`learn/`、`guides/cli.md`、
  `architecture/p1-decisions.md`、相关开发者与状态页面；
- 接入关系：CLI 手册只解释现有 interface/application 行为，精确契约仍由 F-0005、Schema、代码和
  测试维护；架构取舍回链 ADR，不建立第二套决定记录；
- 重点测试：从首页到 CLI/架构/代码/状态的导航，实际 CLI help，过时实现状态搜索，Markdown 链接
  与 Starlight 构建；
- 验证：`uv run python scripts/check_docs.py`、`uv run pytest tests/unit/test_check_docs.py`、
  `npm.cmd run build --prefix=site`、CLI help smoke；
- 回退：恢复导航和改写页面；不影响 Runtime、Event、SQLite 或用户 Artifact。

### 第 7 步：把站点重构为一本面向 Agent 初学者的书

- 状态：completed（2026-08-25）；
- 目标结果：从 README 到站点形成“序章—六部分—附录”的连续路线；首页从读者问题分流；历史页、
  PyPI 和发布资料移入附录；工程 `docs/` 的索引、配置、部署和当前 F-0015 状态同步说人话；
- 视觉结果：两张 GPT Image 插画以 3840×2160 入库，只承担章节气氛和整体印象；精确流程继续使用
  Mermaid；统一排版、卡片、表格和移动端裁切；
- 事实核对：完整阅读 `docs/`、站点、当前代码和测试入口，修复 F-0017 后仍残留的旧状态、参考书章节
  漂移与 Pages 状态混淆；
- 验证：工程链接、Starlight build、资源尺寸、桌面与 390px 手机浏览器检查、Python 全量质量门；
- 回退：可以独立回退内容、样式和插画，不修改 Runtime、Event、SQLite、用户配置或 Artifact。

完成结果：README、工程入口和 43 篇中文内容页已逐页复核；侧边栏重组为序章、六部分和附录；两张
插画以 3840×2160 入库；所有站内 Markdown 链接改成带 `/BearAgent/zh-cn/` 的真实路由。浏览器检查
还发现旧检查器只验证源码文件存在，却允许线上 404 的 `.md` 链接；检查器现已覆盖 MDX、源码后缀
路由和基础路径，并加入回归测试。

## 每一步都检查过

- [x] 站点无 Runtime 持久状态，产物可从源码重建；
- [x] 不读取密钥和用户数据，不增加发布凭证或远程脚本；
- [x] Pages 使用 GitHub 原生身份，只申请 `contents: read`、`pages: write` 和 `id-token: write`；
- [x] CI 只运行有限安装和静态构建；
- [x] Astro telemetry 禁用，只保留构建日志；
- [x] Node 工具链与 Python Runtime 分开；
- [x] 学习、开发、状态和阶段页面同步；
- [x] 术语在具体行为中解释，未使用机械字符串替换。
- [x] CLI 使用说明与实现导读分开，初学者不需要先读 Feature 历史才能运行 P1；
- [x] 已接通的 Agent Loop、workspace Tool 和 CLI 没有继续被写成“尚未实现”。

## 最终验证

```text
npm --prefix=site ci
npm run build --prefix=site
uv run pytest tests/unit/test_check_docs.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
git diff --check
```

静态构建、搜索、Mermaid、工程检查和内容连贯性已经在本地验证。Pages Source 配置完成、workflow
成功且公开 URL 可访问后，再把第 5 步和本 Plan 改为 `completed`。

2026-08-25 本轮验证：`uv lock --check`、Ruff format/check、Pyright、449 tests、三个 Schema 生成器
无内容漂移、137 份 Markdown/MDX 链接、45 页 Starlight + Pagefind + sitemap、全部构建后站内 href、
3840×2160 资源尺寸、sdist/wheel 和隔离 CLI smoke 通过。桌面与 390×844 手机视口检查了首页、六部
侧边栏、Runtime 插画、代码块和 Mermaid；未发现遮挡或不可控溢出。Plan 仍保持 `active`，唯一未完成
项是第 5 步的真实 Pages 上线验收。
