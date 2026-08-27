---
title: "Implementation Plan: Local Starlight documentation site"
status: completed
plan_id: PLAN-F-0015
related_spec: F-0015
created: 2026-08-10
last_updated: 2026-08-27
---

# PLAN-F-0015：建立并重写 Starlight 文档站

关联 Spec：`docs/specs/F-0015-local-starlight-docs-site.md`

## 开始前确认

F-0015 与 ADR-0008 已接受。`docs/` 保存工程事实，`site/` 面向读者解释这些事实。站点只负责展示
文档，可以本地开发、构建和预览；托管平台与线上部署不在本 Plan 中。

## 实施步骤

### 第 1 步：明确工程文档和站点的分工

- 状态：completed；
- 结果：`docs/` 保存精确事实，`site/` 按读者任务解释，不建立第二套 Feature 状态；
- 验证：工程 Markdown 链接和逐段事实核对；
- 回退：删除新增治理说明和索引登记，不影响 Runtime。

### 第 2 步：建立可重复的本地构建

- 状态：completed；
- 结果：Starlight、中文路由、Pagefind、Mermaid、npm scripts 和普通 CI；
- 代码落点：`site/`、package lock 和 `.github/workflows/ci.yml`；
- 验证：`npm --prefix=site ci`、`npm run build --prefix=site`；
- 回退：删除 `site/`，不影响 Python 依赖和数据。

### 第 3 步：用一次任务组织学习与架构内容

- 状态：completed；
- 结果：首页、学习路径、Agent 基础、Runtime 架构、Feature 导读和当前状态；
- 接入关系：学习页先讲具体行为，架构页解释 port/adapter，开发者页连接代码与测试；
- 验证：站点构建、路由和人工连续阅读。

### 第 4 步：把文档同步和写作质量加入完成标准

- 状态：completed；
- 结果：每个 Feature 判断工程事实、学习页、开发者页和状态影响，更新路径或记录 `N/A`；禁止机械
  术语替换；
- 代码落点：`AGENTS.md`、开发 SOP、模板和站点开发者页；
- 验证：链接、站点构建、变更段落连续阅读和完整工程回归。

### 第 5 步：生成可部署到自有服务器的静态站点

- 状态：completed（2026-08-25）；
- 结果：删除原有平台专用部署 workflow、平台域名和 `/BearAgent` 仓库基础路径；
- 结果：根页跳转到 `/zh-cn/`，站内链接和资源从站点根路径加载；
- 结果：CI 只构建，不申请部署权限，也不需要部署凭据；
- 结果：未来使用项目自己的服务器，部署参数由后续独立范围确定；
- 代码落点：`site/astro.config.mjs`、站内路由、`.github/workflows/` 和 `scripts/check_docs.py`；
- 验证：生产构建、全部构建后 href、中文 404、工程链接和 Python 回归；
- 回退：不回退到平台专用配置；自有服务器部署另开 Feature。

### 第 6 步：重组 P1 阅读路径并独立维护 CLI 手册

- 状态：completed（2026-08-23）；
- 结果：首页先把读者带到 CLI 和当前状态；学习路径按“角色分工 → 完整 Run → 状态与边界”深入；
- 结果：新增独立 CLI 手册与 P1 架构取舍页；
- 验证：实际 CLI help、过时实现状态搜索、Markdown 链接与 Starlight 构建。

### 第 7 步：把站点重构为一本面向 Agent 初学者的书

- 状态：completed（2026-08-25）；
- 结果：README、首页和侧边栏形成“序章—六部分—附录”的连续路线；
- 结果：历史、PyPI 和发布资料进入附录，CLI、Runtime 链路、源码路线和状态保持主要入口；
- 视觉：两张 GPT Image 插画以 3840×2160 入库；精确流程继续使用 Mermaid；
- 事实核对：逐页检查当前代码、测试和 P1 实现状态，修复 F-0017 后残留的旧描述；
- 验证：桌面与 390px 手机视口、资源尺寸、路由、构建和 Python 全量质量门。

浏览器检查还发现旧文档检查器只验证 `.md` 源文件存在，却允许构建后指向源码或错误相对路径。
检查器现已覆盖 MDX、真实 `/zh-cn/` 路由、旧 `/BearAgent` 前缀和 pytest 临时目录，并有回归测试。

### 第 8 步：把 Spec 状态和文档影响变成可检查规则

- 状态：completed（2026-08-27）；
- 结果：Spec Front Matter 保持 Feature 状态唯一来源，不新增 `features.yaml` 或外部 Spec CLI；
- 结果：治理检查校验 Feature/Plan/ADR 的 ID、状态关系、索引、完成清单和站点内部 `sourceRefs`；
- 结果：S1 使用精简 Spec，只有多片实施时才写 Plan；S2 使用完整 Spec、ADR 和 active Plan；
- 结果：文档同步从“所有页面都修改”变为“所有表面都判断，更新路径或记录 `N/A` 原因”；
- 代码落点：`scripts/check_governance.py`、单元测试、CI、`AGENTS.md`、SOP、模板和 PR 模板；
- 验证：治理单元测试、当前仓库治理检查、完整 Python 质量门和站点构建；
- 回退：可以移除检查步骤，但保留精简 Spec 和影响判断规则，不恢复平行状态副本。

## 每一步都检查过

- [x] 站点无 Runtime 持久状态，产物可从源码重建；
- [x] 不读取密钥和用户数据，不增加部署凭据或远程脚本；
- [x] 仓库没有文档自动部署 workflow；
- [x] CI 只运行有限安装和静态构建；
- [x] Astro telemetry 禁用，只保留构建日志；
- [x] Node 工具链与 Python Runtime 分开；
- [x] 学习、开发、状态和阶段页面同步；
- [x] CLI 使用说明与实现导读分开；
- [x] 已接通的 Agent Loop、workspace Tool 和 CLI 没有继续写成“尚未实现”。
- [x] Spec、Plan、ADR、索引和站点内部 Feature/ADR/Plan 引用通过治理检查。

## 最终验证

```text
npm --prefix=site ci
npm run build --prefix=site
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
uv run python scripts/check_governance.py
git diff --check
```

2026-08-25 的书籍化版本已验证 Ruff、Pyright、450 tests、Schema 无内容漂移、Markdown/MDX 链接、
Starlight + Pagefind 构建、全部构建后站内 href、两张 3840×2160 资源、sdist/wheel、隔离 CLI smoke，
以及桌面与 390×844 手机视口。删除托管平台假设后，相关路由检查、450 tests、站点构建、45 页构建
产物 href/src 检查，以及桌面和手机浏览器检查再次通过。F-0015 的 Spec 保持 `implemented`，本 Plan
保持 `completed`。2026-08-27 的治理优化另通过 Ruff、Pyright、459 tests、107 个 Markdown 文件链接
检查、12 个 Spec / 11 个 Plan / 15 个 ADR 的治理检查，以及 45 页 Starlight 生产构建。
