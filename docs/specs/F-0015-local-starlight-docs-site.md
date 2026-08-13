---
title: "Feature: Local Starlight documentation site"
status: implemented
spec_id: F-0015
milestone: P1
owner: CherryYang05
created: 2026-08-10
last_updated: 2026-08-13
implemented_in: "PR #3"
related_adrs:
  - ADR-0008
---

# F-0015：建立本地中文文档站

## 1. 为什么现在要做

工程 `docs/` 保存精确的 Architecture、Roadmap、Spec、ADR 和 Plan，适合设计和审查，却没有从
Agent 原理走向代码的学习路径，也缺少公共导航、本地搜索和网站预览。

P1 期间需要先建立内容与技术底座。服务器发布等 P1 完成后单独验收，避免文档部署干扰 Runtime
Feature。

## 2. 本次交付

- G-1：可本地运行和构建的 Starlight 静态站；
- G-2：简体中文内容和稳定 `/zh-cn/` URL；
- G-3：从一次 Agent 任务到 BearAgent 架构和代码的学习路径；
- G-4：页面明确区分通用原理、已接受设计、当前实现和计划；
- G-5：锁定安装、生产构建和 CI 检查；
- G-6：把学习页、开发者页和状态页同步纳入 Feature 完成标准。

## 3. 本次不做

不发布 `docs.bearguin.cn`，不修改 DNS、反向代理或服务器；不完成整套教程、英文翻译、历史版本、
问答 Agent、评论、登录和分析后台；不改变任何 Runtime 行为。

站点不把 Spec 原文复制成教程，也不使用逐词替换制造新的术语。

## 4. 需要先说明的约定

`docs/`、代码和测试保存工程事实；`site/` 根据这些事实组织学习和代码阅读内容。本地运行表示开发者
能启动预览并生成静态页面，不表示服务器已上线。第一版只维护简体中文。

## 5. 使用场景

### 从一次任务开始学习

读者打开首页后，可以从一个仓库文件任务出发，逐步理解模型、Runtime、Event、Reducer、port 和
adapter，而不是先面对完整术语表。

### 开发者本地预览

安装受支持 Node.js 后，开发者按 lockfile 安装依赖，在 `/zh-cn/` 预览修改，并能构建最终页面与
搜索索引。

### 构建阻止损坏页面

Front Matter、内部链接、MDX 或 Mermaid 无法编译时，生产构建失败，不生成表面成功的站点。

### Feature 关闭

一个 Feature 准备标记完成时，工程事实、相关学习说明、代码导读和当前状态已经同步；整个阶段
关闭时再更新学习地图和阶段结果。

## 6. 必须满足的行为

- FR-1：站点位于根目录 `site/`，Node 依赖和产物不进入 Python 包；
- FR-2：使用 Starlight 和提交的 `package-lock.json`；
- FR-3：中文内容位于 `/zh-cn/`，导航覆盖开始、学习、架构、开发、项目、指南和参考；
- FR-4：首页提供学习、架构、开发和当前状态入口；
- FR-5：第一版包含学习路径、Agent 基础、架构、F-0001 导读、状态和参考资料；
- FR-6：页面标明内容状态，计划能力不得写成当前实现；
- FR-7：全文搜索不依赖外部 SaaS；
- FR-8：支持 Mermaid，依赖锁定并通过构建；
- FR-9：提供本地开发、构建和生产预览命令；
- FR-10：CI 锁定安装并构建，但不部署；
- FR-11：每个 Feature 同步工程 `docs/`、学习页、开发者页和状态页；
- FR-12：每个阶段关闭时同步 Roadmap、学习地图、架构总结和阶段结果；
- FR-13：外部资料优先一手来源，star 只用于发现项目；
- FR-14：文档先讲具体问题和行为，再引入必要术语；禁止用机械替换代替上下文重写。

## 7. 对外入口和模块连接

```text
npm --prefix=site ci
npm run dev --prefix=site
npm run build --prefix=site
npm run preview --prefix=site
```

不新增 BearAgent CLI、Python API、Tool、Event 或数据库 schema。

## 8. 状态和保存的数据

内容、配置和静态资源进入 Git。`site/dist/` 可以从源码重新生成，不提交。页面元数据只服务内容
显示，不成为 Runtime 数据；Feature 状态继续由工程 Spec 管理。

## 9. 失败时会发生什么

lockfile 安装失败、Markdown/MDX 编译失败、无效 Front Matter 或 Mermaid 错误都会让构建失败。
本地预览中断后重新启动即可。产物损坏时删除 `site/dist/` 并重新构建，不从产物恢复源内容。

## 10. 安全与隐私

站点不需要 Provider key、用户数据或 Runtime 数据；不嵌入密钥、远程脚本、评论、分析追踪或动态
后端。依赖更新必须审查 lockfile 并重新构建。

## 11. 怎样检查执行过程

只保留本地和 CI 构建输出，不添加用户遥测。Git `lastUpdated` 帮助判断页面新鲜度，但不替代
Feature 状态。

## 12. 上线与回退

P1 只支持本地与 CI。P1 完成后另行决定托管、域名、HTTPS、发布权限和回滚。回退 F-0015 时删除
`site/` 和 Node CI 步骤，不涉及 Runtime 数据迁移。

## 13. 验收标准

- AC-1：F-0015 不修改 F-0001 Runtime 代码和测试；
- AC-2：`npm --prefix=site ci` 可从 lockfile 安装；
- AC-3：生产构建生成 `/zh-cn/` 页面和本地搜索索引；
- AC-4：首页和侧边栏能到达必要页面；
- AC-5：至少一张 BearAgent Mermaid 图能渲染；
- AC-6：状态页准确区分已实现和 Roadmap；
- AC-7：CI 构建但不部署，不含服务器凭证；
- AC-8：Python 检查、测试和工程链接继续通过；
- AC-9：仓库规则、SOP、模板和 PR 模板要求同步各文档入口；
- AC-10：开发者入口、Feature 文档规则和实现导读与学习路径互链；
- AC-11：站点与工程文档的改写以完整段落为单位，术语在具体行为中解释。

## 14. 验证方式

- Contract：lockfile 安装和生产构建；
- Integration：CI 同时运行 Python 检查和站点构建；
- Recovery：删除静态产物后从源码重建；
- Security：检查 diff 和配置不含密钥、发布步骤或 Runtime 数据；
- Manual：本地检查导航、搜索、状态提示、Mermaid 和段落连贯性。

## 15. 文档同步

- [x] Engineering docs
- [x] Site learning path
- [x] Site developer docs
- [x] Site status and milestones
- [x] Architecture / ADR
- [x] Deployment docs
- [ ] Generated reference

## 16. 尚未决定的问题

无。Starlight、中文优先和 P1 仅本地构建已确认。
