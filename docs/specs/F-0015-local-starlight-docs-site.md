---
title: "Feature: Local Starlight documentation site"
status: implemented
spec_id: F-0015
milestone: P1
owner: CherryYang05
created: 2026-08-10
last_updated: 2026-08-10
implemented_in: null
related_adrs:
  - ADR-0008
---

# Feature: Local Starlight documentation site

## 1. Background / Problem

仓库现有 `docs/` 是面向实现者的工程事实来源，包含 Architecture、Roadmap、Feature Spec、
ADR 和 Implementation Plan。它适合设计审查，但缺少面向初学者的学习路径、公共导航、
站内搜索和本地可预览的网站体验。

BearAgent 需要在 P1 期间建立公共文档的内容与技术底座，让 Agent 原理、BearAgent 架构和
已实现 Feature 可以被逐步讲解；服务器发布必须等 P1 完成后单独验收，不能让早期站点增加
当前运行时 Feature 的交付风险。

## 2. Goals

- G-1：建立独立、可本地运行和构建的 Starlight 静态文档站。
- G-2：以中文为第一语言，并从第一天保留稳定的 `/zh-cn/` URL 空间。
- G-3：提供从 Agent 基础原理到 BearAgent 架构和代码的初学者学习入口。
- G-4：明确区分通用原理、BearAgent 已接受设计、当前实现和未来规划。
- G-5：将文档站构建纳入可重复的本地命令和 CI 检查。

## 3. Non-goals

- NG-1：本 Feature 不发布 `docs.bearguin.cn`，不修改 DNS、反向代理或服务器。
- NG-2：不在第一版完成整套 Agent 教程、英文翻译或历史版本文档。
- NG-3：不提供文档问答 Agent、评论、登录、分析后台或其他动态服务。
- NG-4：不把 Spec、ADR 和 Roadmap 原样复制后就宣称已经形成初学者教程。
- NG-5：不改变 F-0001 或其他运行时 Feature 的实现和公开契约。

## 4. Terms and assumptions

- `docs/`：工程 Source of Truth，由开发治理流程维护。
- `site/`：公共教学与使用文档的 Starlight 工程，以 `docs/`、代码和测试为事实来源。
- “本地部署”：开发者可在本机启动预览服务并生成完整静态站点，不表示服务器已上线。
- 第一版只维护简体中文；`en` 路径保留到真实翻译工作开始时再创建内容。

## 5. User scenarios

### Scenario A：初学者选择学习路径

Given 读者打开本地文档首页，When 选择“理解 Agent”或“理解 BearAgent 架构”，Then 可以
进入对应的中文学习路径，并看到每页描述的是原理、当前实现还是规划能力。

### Scenario B：开发者本地预览

Given 开发者已安装受支持的 Node.js，When 在 `site/` 安装锁定依赖并启动开发服务器，Then
可以在浏览器访问 `/zh-cn/`，编辑 Markdown/MDX 后看到本地更新。

### Scenario C：构建阻止文档损坏

Given 文档包含无效 Front Matter、内部链接或无法编译的页面，When 执行生产构建，Then
构建失败而不是生成一个表面成功但内容损坏的站点。

## 6. Functional requirements

- FR-1：站点工程位于仓库根目录的 `site/`，Node 依赖和构建产物不得进入 Python 包。
- FR-2：使用 Astro Starlight，并提交 `package-lock.json` 以提供可重复依赖安装。
- FR-3：默认中文内容位于 `/zh-cn/`，导航至少包含开始、学习、架构、指南、参考和项目。
- FR-4：首页提供“理解 Agent、运行 BearAgent、理解架构、参与开发”四个入口。
- FR-5：第一版至少包含学习路径、Agent 基础、架构概览、F-0001 导读、当前状态和参考来源。
- FR-6：页面通过 Front Matter 或统一组件标明内容状态，不把规划能力写成当前实现。
- FR-7：提供无需外部搜索服务的本地全文搜索。
- FR-8：支持仓库现有的 Mermaid 图表写法；相关集成必须锁定版本并通过构建验证。
- FR-9：提供本地开发、生产构建和生产预览命令，并在站点 README 中说明。
- FR-10：CI 在不发布静态产物的前提下执行锁定安装与生产构建。

## 7. Interfaces

新增文档开发命令：

```text
npm --prefix=site ci
npm run dev --prefix=site
npm run build --prefix=site
npm run preview --prefix=site
```

不新增 BearAgent CLI、Python API、HTTP API、Tool、Event 或数据库 schema。

## 8. State and data model

- 站点内容、配置和静态资源均在 Git 中版本化。
- 构建产物 `site/dist/` 是可丢弃输出，不提交 Git。
- 页面元数据用于内容分类和显示，不成为运行时领域数据。
- `docs/` 继续拥有 Feature 状态和架构事实；`site/` 不创建第二套 Feature 状态数据库。

## 9. Failure and recovery semantics

- 依赖无法按 lockfile 安装时，本地或 CI 构建失败。
- Markdown/MDX、Front Matter、内部路由或 Mermaid 无法编译时，构建失败。
- 本地预览中断不会影响 BearAgent 数据或运行时；重新启动开发服务器即可恢复。
- 构建产物损坏时删除 `site/dist/` 并从已提交源码重新生成，不从产物反向恢复内容。

## 10. Security and privacy

- 站点构建和运行不得需要 Provider key、用户数据或 BearAgent runtime data。
- 不在页面、前端 bundle、构建日志或示例中嵌入 secret。
- 第一版不添加任意远程脚本、评论系统、分析追踪或动态后端。
- Mermaid 和其他扩展按固定依赖版本安装；依赖更新必须经过 lockfile 审查和构建验证。

## 11. Observability

- 本 Feature 只需要可读的本地构建错误和 CI 结果。
- 不添加用户分析、遥测或远程错误采集。
- 页面 `lastUpdated` 用 Git 时间帮助读者判断内容新鲜度，但不替代 Feature 状态。

## 12. Rollout and rollback

- P1 期间只支持本地开发、生产构建和 CI 验证。
- P1 完成后另行确认托管方式、域名、HTTPS、发布权限和回滚，再发布到服务器。
- 回滚 F-0015 时删除 `site/`、Node CI 步骤和对应文档登记；不涉及运行时数据 migration。

## 13. Acceptance criteria

- AC-1：分支基于 F-0001 已完成提交，且 F-0001 代码和测试不被修改。
- AC-2：`npm --prefix=site ci` 可从 lockfile 安装依赖。
- AC-3：`npm run build --prefix=site` 成功并生成 `/zh-cn/` 静态页面与本地搜索索引。
- AC-4：本地站点包含 FR-5 的页面，并能从首页和侧边栏到达。
- AC-5：至少一张 BearAgent Mermaid 架构图在站点中渲染。
- AC-6：当前状态页明确 F-0001 已实现，其余能力按仓库 Roadmap 标记为规划中。
- AC-7：CI 构建站点但不执行部署，不包含服务器凭证或发布权限。
- AC-8：Python 质量检查、测试和工程 Markdown 链接检查继续通过。

## 14. Test plan

- Unit：不新增运行时单元测试；由 Starlight schema 和构建器校验页面配置。
- Contract：lockfile 安装和生产构建作为文档工程契约。
- Integration：CI 同时运行 Python 质量检查与站点构建。
- Recovery：删除静态产物后从源码重新构建。
- Security：检查仓库 diff、前端配置和 CI 不包含 secret、远程发布步骤或 runtime data。
- Eval/manual：本地访问 `/zh-cn/`，检查导航、搜索、状态提示和 Mermaid。

## 15. Documentation impact

- [x] Architecture
- [x] ADR
- [x] User docs
- [x] Deployment docs
- [ ] Generated reference

## 16. Open questions

None. Starlight、中文优先和 P1 期间仅本地部署已由项目所有者确认。
