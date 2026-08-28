---
title: 在本地查看文档站
description: 安装锁定依赖，启动开发预览，并验证搜索和生产构建。
bearStatus: implemented
sourceRefs:
  - F-0015
---

F-0015 把学习内容和开发者文档组织成一份独立静态站点。它不运行 BearAgent Runtime，也不需要
模型密钥或 BearAgent 数据。

## 准备环境

- Node.js 22.12 或更新版本；
- npm 9.6.5 或更新版本。

## 开发预览

在仓库根目录执行：

```powershell
npm --prefix=site ci
npm run dev --prefix=site
```

然后访问 `http://localhost:4321/zh-cn/`。Markdown 或 MDX 保存后会自动刷新。

## 验证生产页面和搜索

开发模式不会生成 Pagefind 搜索索引。要检查最终页面和搜索，执行：

```powershell
npm run build --prefix=site
npm run preview --prefix=site
```

生产预览的根路径会跳转到 `/zh-cn/`。构建产物位于 `site/dist/`，可以随时从源码重新生成。

## 为什么站内链接从 `/zh-cn/` 开始

第一版只维护简体中文，所以正文路由统一从 `/zh-cn/` 开始。站点不绑定仓库名、域名或托管平台，
脚本、样式和图片也从站点根路径加载。普通 CI 只验证构建，不会部署 `site/dist/`。

:::caution[不要提交生成目录]
`site/node_modules/`、`site/.astro/` 和 `site/dist/` 都不进入 Git。
:::

## 写页面时

工程事实来自仓库文档、代码和测试。页面先用一个具体场景解释，再引入必要术语；不要逐词翻译
工程文档，也不要把未来路线写成当前功能。每页的 `bearStatus` 和 `sourceRefs` 用于
标记内容性质和事实来源。

完整关闭流程见[Feature 完成时怎样更新文档](/zh-cn/development/feature-documentation/)。

## 提交前做一次视觉检查

至少查看首页和一篇含 Mermaid/代码块的长页面：

1. 桌面宽度确认侧边栏、正文、目录和 4K 插画层级清楚；
2. 390px 手机宽度确认导航可打开，图片裁切不遮挡说明，代码块可横向滚动；
3. 明暗主题各看一次对比度；
4. 只用键盘确认主要入口可以聚焦；
5. 生产 build 后再检查一次，避免开发模式掩盖路由或搜索问题。
