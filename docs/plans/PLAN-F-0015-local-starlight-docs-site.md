---
title: "Implementation Plan: Local Starlight documentation site"
status: completed
plan_id: PLAN-F-0015
related_spec: F-0015
created: 2026-08-10
last_updated: 2026-08-10
---

# Implementation Plan: Local Starlight documentation site

Related Spec: `docs/specs/F-0015-local-starlight-docs-site.md`

## Preconditions

- Spec status is `accepted`.
- ADR-0008 is accepted.
- Starlight、中文优先和 P1 期间仅本地部署已确认。
- 分支从 F-0001 的已完成提交创建。

## Vertical slices

### Slice 1: 文档治理与站点边界

- Status：completed。
- Domain/contracts：定义 `docs/` 工程事实与 `site/` 公共教学内容的职责。
- Adapter/interface：登记 F-0015、ADR-0008、Plan 和 Roadmap。
- Tests：工程 Markdown 链接检查。
- Verification command：`uv run python scripts/check_docs.py`。
- Rollback point：删除新增治理文档和索引登记，不影响 F-0001。

### Slice 2: 可重复的本地 Starlight 构建

- Status：completed。
- Domain/contracts：定义站点目录、中文路由和本地命令。
- Adapter/interface：Starlight、Pagefind、Mermaid 和 npm scripts。
- Tests：lockfile 安装、生产构建、静态输出检查。
- Verification command：`npm --prefix=site ci` 和 `npm run build --prefix=site`。
- Rollback point：删除 `site/`；不涉及 Python 依赖或运行时数据。

### Slice 3: 第一批学习与架构内容

- Status：completed。
- Domain/contracts：页面状态区分原理、设计、当前实现和规划。
- Adapter/interface：首页、导航、学习路径、架构、F-0001、状态与来源页。
- Tests：Starlight build、路由存在性和人工导航检查。
- Verification command：`npm run build --prefix=site`。
- Rollback point：保留站点骨架，逐页回退内容。

### Slice 4: CI、文档同步与关闭

- Status：completed。
- Domain/contracts：无运行时变化。
- Adapter/interface：CI 只构建不部署；README/SOP/Architecture 与当前事实同步。
- Tests：完整 Python 质量检查、测试、工程文档链接和站点构建。
- Verification command：Definition of Done 全部命令。
- Rollback point：移除 Node CI job，保留可本地使用的站点。

## Cross-cutting checks

- [x] Persistence/recovery：站点无持久状态；构建产物可从源码重建。
- [x] Permission/security：不读取 secret/runtime data，不添加发布凭证或远程脚本。
- [x] Timeout/cancel/resource limits：CI 只执行有限的安装和静态构建，不启动预览进程。
- [x] Logs/trace/metrics：构建脚本禁用 Astro telemetry，只保留本地/CI 构建输出。
- [x] Migration/rollback：新目录隔离，可整体删除；没有数据库 migration。
- [x] Documentation impact：已同步 Architecture、Roadmap、SOP、部署策略和本地使用说明。

## Final verification

```text
npm --prefix=site ci
npm run build --prefix=site
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
git diff --check
```

本 Plan 只有在静态中文页面、搜索、Mermaid、CI 和全部回归检查通过后才标记 `completed`。
