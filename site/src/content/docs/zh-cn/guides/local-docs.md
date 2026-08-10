---
title: 本地运行文档站
description: 安装锁定依赖并在本机预览 BearAgent 的 Starlight 文档。
bearStatus: implemented
sourceRefs:
  - F-0015
  - ADR-0008
---

F-0015 只建立本地文档站和 CI 构建，不发布服务器。

## 环境要求

- Node.js 22.12 或更新版本
- npm 9.6.5 或更新版本

## 安装与开发预览

在仓库根目录执行：

```powershell
npm --prefix=site ci
npm run dev --prefix=site
```

然后访问 `http://localhost:4321/zh-cn/`。

## 验证生产构建与搜索

开发模式不生成 Pagefind 搜索索引。要验证实际搜索体验，应构建并预览生产产物：

```powershell
npm run build --prefix=site
npm run preview --prefix=site
```

生产预览默认位于 `http://localhost:4321/`，根路径会跳转到 `/zh-cn/`。

:::caution[不要提交生成物]
`site/node_modules/`、`site/.astro/` 和 `site/dist/` 都是可重新生成的本地目录，不进入 Git。
:::

## 文档事实从哪里来

公共文章应根据仓库中的 Architecture、Spec、ADR、代码和测试改写。聊天记录和未来 Roadmap 不能
被直接描述成当前能力；每个页面必须声明 `bearStatus` 和 `sourceRefs`。

每个 Feature 还必须同时检查初学者学习路径、开发者实现导读和当前状态页，完整流程见
[Feature 与阶段的文档同步](../development/feature-documentation.md)。
