---
title: "ADR-0008: Starlight for the public documentation site"
status: accepted
date: 2026-08-10
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0008：公共文档站使用 Starlight

## Context

BearAgent 已有以 Markdown 编写的 Architecture、Spec、ADR 和 Plan，但公共文档需要学习路径、
中文导航、本地搜索、状态提示和可定制首页。该选择引入独立 Node 工具链和公开内容边界，
以后还会影响托管、国际化和版本管理，属于需要显式记录的 S2 决策。

Material for MkDocs 已进入维护模式；其继任者 Zensical 仍处于 alpha，国际化和版本化能力尚未
稳定。Docusaurus 能力完整但引入 React SPA/MDX 工程和以 Algolia 为主的官方搜索路径；
VitePress 简洁，但其 Vue 定制能力没有给当前 Python 项目带来直接收益。

## Decision drivers

- 可维护性：内容作者应主要编写 Markdown/MDX，前端代码保持最少。
- 本地优先：全文搜索和预览不依赖外部 SaaS。
- 国际化：从第一天保留 `/zh-cn/`，以后可增加英文而不迁移中文 URL。
- 内容表达：支持教学卡片、提示、代码和 Mermaid 架构图。
- 安全：生成静态站点，不读取 runtime data 或 secrets。
- 生命周期：新站点应使用仍在积极发展的框架，不以维护模式项目为长期基座。

## Considered options

### Option A：Astro Starlight

优点：文档功能开箱即用；内置 Pagefind 本地搜索和多语言路由；Astro 允许定制首页但默认输出
静态站点；MIT License。

缺点：增加 Node/npm 工具链；Mermaid 依赖社区集成；没有必要在 P1 就使用其全部扩展能力。

### Option B：Docusaurus

优点：成熟；国际化、版本文档和 Mermaid 支持完整；React 生态强。

缺点：对当前需求偏重；官方搜索的首选是外部 Algolia；自定义容易扩大为 React 产品工程。

### Option C：VitePress

优点：构建快；本地搜索和国际化简单；默认主题适合技术文档。

缺点：深度定制围绕 Vue；版本化和 Mermaid 需要额外约定，没有胜过 Starlight 的当前需求。

### Option D：Material for MkDocs 或 Zensical

优点：与现有 Python/Markdown 习惯接近，参考文档站使用同类界面。

缺点：Material 处于维护模式；Zensical 当前仍是 alpha。新项目不应立即承担可预见的迁移。

## Decision

- 公共文档站使用 Astro Starlight，代码和内容位于独立 `site/` 目录。
- 使用 npm 和提交的 `package-lock.json` 管理站点依赖；Python 继续只使用 uv。
- 中文内容使用 `/zh-cn/`；第一版不创建内容为空的英文站点。
- 使用 Starlight 默认 Pagefind 搜索，不接入外部搜索或分析服务。
- Mermaid 通过锁定的最小集成支持，必须由生产构建验证。
- `docs/` 保持工程 Source of Truth；`site/` 提供教学改写并链接到工程证据。
- `site/` 同时维护初学者学习路径与开发者实现文档。每个 Feature 必须更新两条路径和当前状态；每个 P 阶段还要更新阶段总结。
- 外部资料优先使用论文、规范、官方文档和官方仓库。GitHub star 仅用于发现参考项目，不构成 BearAgent 的架构证据。
- F-0015 只交付本地预览、静态构建和 CI，不部署服务器。

## Consequences

### Positive

- 可以快速得到适合教程、架构和参考内容的现代文档体验。
- 搜索和静态站点可以完全在本地构建，不增加运行时服务。
- 公共内容与工程治理文档拥有清晰边界。
- 将来可使用 Astro 组件扩展交互示例，而无需重写 Markdown 内容。

### Negative / debt accepted

- 仓库出现 Python/uv 与 Node/npm 两套工具链，CI 需要分别验证。
- Mermaid 集成不是 Starlight 核心能力，需要固定版本并关注维护状态。
- 如果未来强依赖多版本文档，需重新比较 Starlight 方案与 Docusaurus。

## Migration and rollback

当前没有公共站点和已发布 URL，不存在内容或访问迁移。回滚时删除 `site/` 与 Node CI job，
工程 `docs/` 不受影响。P1 完成后的服务器发布必须另行记录托管和发布决策。

## Validation

- 使用 lockfile 在本地和 CI 安装依赖。
- 生产构建必须生成中文页面、Pagefind 索引和 Mermaid 页面。
- 检查静态站点不需要 API key、数据库或运行时服务。
- 当出现必须维护多个已发布 BearAgent 版本的真实需求，或 Zensical 达到稳定版本时重新评估。
