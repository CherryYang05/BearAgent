---
title: "ADR-0008: Use Starlight for the public documentation site"
status: accepted
date: 2026-08-10
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0008：公共文档站使用 Starlight

## 要解决的问题

工程 `docs/` 适合记录精确需求和决定，但不适合直接充当初学者教程。公共站点需要中文导航、本地
搜索、状态提示、Mermaid 和可定制首页，同时不能读取 Runtime 数据或依赖外部搜索服务。

## 选择时最看重什么

- 内容作者主要写 Markdown/MDX，前端代码尽量少；
- 搜索和预览可以完全在本地工作；
- 中文 URL 从第一天稳定在 `/zh-cn/`；
- 产物是静态文件，不需要动态后端；
- 框架仍在积极维护。

## 比较过的方案

- Starlight 提供文档导航、Pagefind 搜索和多语言路由，Astro 允许小范围定制；代价是新增 Node/npm；
- Docusaurus 功能成熟，但 React 工程和外部搜索路径对当前需求偏重；
- VitePress 简洁，但 Vue 定制和版本能力没有带来明显优势；
- Material for MkDocs 已进入维护模式，Zensical 当时仍处于 alpha。

## 决定

站点位于 `site/`，使用 Starlight、npm 和提交的 `package-lock.json`。中文内容放在 `/zh-cn/`，使用
Pagefind 和锁定版本的 Mermaid 集成，不接远程分析或搜索。

工程事实仍由 `docs/`、代码和测试确认。站点按读者任务重写这些事实，不复制 Spec。每个 Feature
完成时更新相关学习页、开发者页和当前状态；每个阶段完成时再更新学习地图和阶段结果。

F-0015 最初只交付本地预览、静态构建和 CI。2026-08-16 决定把同一份静态产物发布到 GitHub
Pages，先使用 `https://cherryyang05.github.io/BearAgent/`。Astro 的公开地址和基础路径必须写进配置，
避免页面上线后把资源和链接错误地指向域名根目录。

普通 PR 继续只构建。独立 workflow 只在 `main` 或手动触发时发布，使用 GitHub 原生 Pages 身份，
不保存服务器凭证。`docs.bearguin.cn`、DNS 和独立服务器仍不属于本次决定。

## 带来的影响

仓库同时维护 Python/uv 与 Node/npm 两套工具链，CI 需要分别验证。Mermaid 是额外集成，需要关注
版本。得到的好处是本地搜索、中文导航和教学页面可以静态构建并公开访问，不增加 Runtime 服务。
仓库设置中需要把 Pages Source 选为 GitHub Actions；发布失败时继续保留上一份成功产物。

## 怎样验证

从 lockfile 安装后，生产构建必须生成中文页面、Pagefind 索引、Mermaid 图、sitemap 和中文 404；
根页、资源和 sitemap URL 都包含 `/BearAgent/`。构建过程不需要密钥、数据库或用户数据。首次部署后
检查公开 URL。需要维护多个已发布版本时再重新评估框架。
