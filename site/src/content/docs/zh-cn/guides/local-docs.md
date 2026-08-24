---
title: 在本地查看文档站
description: 安装锁定依赖，启动开发预览，并验证搜索和生产构建。
bearStatus: implemented
sourceRefs:
  - F-0015
---

F-0015 的本地预览和 GitHub Pages 使用同一份静态站点。它不运行 BearAgent Runtime，也不需要模型
密钥或 BearAgent 数据。

## 准备环境

- Node.js 22.12 或更新版本；
- npm 9.6.5 或更新版本。

## 开发预览

在仓库根目录执行：

```powershell
npm --prefix=site ci
npm run dev --prefix=site
```

然后访问 `http://localhost:4321/BearAgent/zh-cn/`。Markdown 或 MDX 保存后会自动刷新。

## 验证生产页面和搜索

开发模式不会生成 Pagefind 搜索索引。要检查最终页面和搜索，执行：

```powershell
npm run build --prefix=site
npm run preview --prefix=site
```

生产预览的根路径会跳转到 `/BearAgent/zh-cn/`。构建产物位于 `site/dist/`，可以随时从源码重新生成。

## 在线地址为什么多一段 `/BearAgent`

目标项目 Pages 地址是 `https://cherryyang05.github.io/BearAgent/`，仓库名就是站点的基础路径。Astro 在
构建时为脚本、样式、sitemap 和内部入口加上这段前缀。变更进入 `main` 后，独立 workflow 才会
尝试发布；普通 PR 不会改线上站点。2026-08-25 该公开地址仍返回 404，因此必须把“构建通过”和
“公开可访问”作为两个验收结果分别报告。

:::caution[不要提交生成目录]
`site/node_modules/`、`site/.astro/` 和 `site/dist/` 都不进入 Git。
:::

## 写页面时

工程事实来自仓库文档、代码和测试。页面先用一个具体场景解释，再引入必要术语；不要逐词翻译
工程文档，也不要把未来路线写成当前功能。每页的 `bearStatus` 和 `sourceRefs` 用于
标记内容性质和事实来源。

完整关闭流程见[Feature 完成时怎样更新文档](/BearAgent/zh-cn/development/feature-documentation/)。

## 提交前做一次视觉检查

至少查看首页和一篇含 Mermaid/代码块的长页面：

1. 桌面宽度确认侧边栏、正文、目录和 4K 插画层级清楚；
2. 390px 手机宽度确认导航可打开，图片裁切不遮挡说明，代码块可横向滚动；
3. 明暗主题各看一次对比度；
4. 只用键盘确认主要入口可以聚焦；
5. 生产 build 后再检查一次，避免开发模式掩盖基础路径或搜索问题。
