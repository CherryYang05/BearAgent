---
title: "Feature: Local Starlight documentation site"
status: implemented
spec_id: F-0015
milestone: P1
owner: CherryYang05
created: 2026-08-10
last_updated: 2026-08-25
implemented_in: "PR #3, PR #14, and codex/F-0015-docs-site"
related_adrs:
  - ADR-0008
---

# F-0015：建立可以连续阅读的中文文档站

## 1. 为什么要做

工程 `docs/` 保存精确的 Architecture、Roadmap、Spec、ADR 和 Plan。它适合设计与审查，却不适合让
第一次接触 Agent 的读者从头学习。BearAgent 还需要一份能先运行、再理解原理、最后进入代码的中文
文档站。

`site/` 负责展示这套学习内容。它是独立静态站点，不运行 BearAgent Runtime，也不承担线上部署。

## 2. 本次交付

- G-1：可本地开发、构建和预览的 Starlight 静态站；
- G-2：简体中文内容和稳定的 `/zh-cn/` 路由；
- G-3：从一次 Agent 文件任务走向架构、代码和研究问题的学习路径；
- G-4：页面明确区分通用原理、已接受设计、当前实现和未来计划；
- G-5：锁定依赖、生产构建和普通 CI 检查；
- G-6：每个 Feature 同步学习页、开发者页和当前状态；
- G-7：独立 CLI 手册，不让读者从多个 Spec 中拼出使用方法；
- G-8：序章、六部分和附录组成的书籍结构，并用少量 4K 插画建立章节印象。

## 3. 本次不做

本次不选择 GitHub Pages、域名、服务器或其他托管平台，不添加自动部署 workflow。也不完成英文翻译、
历史版本、问答 Agent、评论、登录和分析后台，不改变任何 Runtime 行为。

站点不复制 Spec 原文，不把未来能力写成当前实现，也不使用逐词替换制造新术语。

## 4. 文档怎样分工

`docs/`、代码和测试保存工程事实；`site/` 根据这些事实组织学习与源码阅读。第一版只维护简体中文。
站点从根路径加载资源，中文页面从 `/zh-cn/` 开始，因此本地预览和任意静态服务器都不需要知道
GitHub 仓库名。

## 5. 读者怎样使用

### 第一次学习 Agent

读者从一个仓库文件任务出发，先看到 Model、Runtime 和 Tool 怎样协作，再逐步理解 Event、Reducer、
port、adapter、安全边界和代码位置。

### 本地查看文档

开发者按 lockfile 安装 Node 依赖，启动开发服务器，在 `/zh-cn/` 阅读和修改内容；生产构建还会生成
本地搜索索引。

### 修改功能后同步文档

一个 Feature 准备关闭时，工程事实、相关学习说明、代码导读和当前状态必须同时更新。整个阶段关闭
时，再更新学习地图和阶段结果。

## 6. 必须满足的行为

- FR-1：站点位于根目录 `site/`，Node 依赖和产物不进入 Python 包；
- FR-2：使用 Starlight 和提交的 `package-lock.json`；
- FR-3：中文内容位于 `/zh-cn/`，导航覆盖开始、学习、架构、开发、项目、指南和参考；
- FR-4：首页能到达 CLI、学习路线、架构、开发者入口和当前状态；
- FR-5：页面标明内容状态，计划能力不得写成当前实现；
- FR-6：全文搜索不依赖外部 SaaS；
- FR-7：支持 Mermaid，依赖锁定并通过构建；
- FR-8：提供本地开发、生产构建和本地预览命令；
- FR-9：普通 CI 锁定安装并构建站点，不执行部署；
- FR-10：每个 Feature 同步工程 `docs/`、学习页、开发者页和状态页；
- FR-11：外部资料优先一手来源，star 只用于发现项目；
- FR-12：文档先讲具体问题和行为，再引入必要术语；
- FR-13：站点不配置托管平台专用域名、仓库基础路径或部署权限；
- FR-14：文档检查在进入目录前排除 `.venv`、pytest 临时目录和其他生成目录；
- FR-15：主导航按“序章—六部分—附录”组织，历史页只能放在附录；
- FR-16：CLI 手册集中说明安装、profile、Provider 配置、命令、输出、退出码、数据位置和常见失败；
- FR-17：每章先回答一个具体问题，再给例子、图、代码入口、验证方法和当前/未来边界；
- FR-18：生成式插画不承载精确标签、代码或安全规则；入库资源达到 3840×2160，有替代文本，并在
  桌面和手机宽度下不遮挡正文。

## 7. 对外入口

```text
npm --prefix=site ci
npm run dev --prefix=site
npm run build --prefix=site
npm run preview --prefix=site
```

不新增 BearAgent CLI、Python API、Tool、Event 或数据库 schema。

## 8. 状态和数据

内容、配置和静态资源进入 Git。`site/dist/` 可以从源码重新生成，不提交。页面元数据只服务内容
显示，不成为 Runtime 数据。

## 9. 失败时会发生什么

lockfile 安装失败、无效 Front Matter、损坏的 Markdown/MDX、Mermaid 或内部路由都会让检查失败。
本地预览中断后重新启动即可；产物损坏时从源码重建，不从 `site/dist/` 恢复源内容。

## 10. 安全与隐私

站点不需要 Provider key、用户数据或 Runtime 数据，不嵌入远程分析、评论或动态后端。仓库没有文档
部署 workflow，因此不需要部署 token、Pages 权限或服务器凭据。依赖更新必须审查 lockfile 并重建。

## 11. 发布边界

F-0015 的“完成”表示文档内容、导航、本地预览、生产构建、搜索和 CI 已通过，不表示某个公网地址
已经上线。如果以后需要在线托管，应另开范围，说明目标平台、URL、权限、回退和公开访问验收。

## 12. 验收标准

- AC-1：F-0015 不修改 Runtime 行为；
- AC-2：`npm --prefix=site ci` 可从 lockfile 安装；
- AC-3：生产构建生成 `/zh-cn/` 页面和本地搜索索引；
- AC-4：首页和侧边栏能到达必要页面；
- AC-5：Mermaid 图可以构建；
- AC-6：状态页准确区分已实现和 Roadmap；
- AC-7：CI 构建站点，但仓库不存在文档自动部署 workflow；
- AC-8：Python 检查、测试和工程链接继续通过；
- AC-9：开发者入口、Feature 文档规则和实现导读与学习路径互链；
- AC-10：站点与工程文档按完整段落重写，不使用机械术语替换；
- AC-11：根页跳转到 `/zh-cn/`，内部路由和资源不含 `/BearAgent/` 仓库前缀；
- AC-12：文档检查不进入生成目录，并有回归测试；
- AC-13：首页、CLI、Runtime 链路、源码路线和状态页从首页最多两次点击可达；
- AC-14：已接通的 Agent Loop、workspace Tool 和 `run/inspect/events` 不再写成尚未实现；
- AC-15：两张插画均为 3840×2160，具有可读 alt；桌面和 390px 手机视口下，首页、导航、
  Mermaid、图片和代码块没有明显溢出或遮挡。

## 13. 验证方式

- Contract：lockfile 安装和生产构建；
- Integration：普通 CI 同时运行 Python 检查和站点构建；
- Recovery：删除静态产物后从源码重建；
- Security：确认没有部署 workflow、凭据或远程分析；
- Manual：本地检查导航、搜索、状态提示、Mermaid、桌面与手机排版。

## 14. 文档同步

- [x] Engineering docs
- [x] Site learning path
- [x] Site developer docs
- [x] Site status and milestones
- [x] Architecture / ADR
- [x] Deployment boundary docs
- [x] Generated reference（本轮无公开 contract 变化）

## 15. 尚未决定的问题

F-0015 没有开放问题。在线托管不是本 Feature 的待办事项。
