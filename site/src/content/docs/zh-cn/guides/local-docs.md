---
title: 在本地查看文档站
description: 安装锁定依赖，启动开发预览，并验证搜索和生产构建。
bearStatus: implemented
sourceRefs:
  - F-0015
  - ADR-0008
---

F-0015 只建立本地文档站和 CI 构建，不发布服务器。运行文档站不需要模型密钥或 BearAgent 数据。

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

:::caution[不要提交生成目录]
`site/node_modules/`、`site/.astro/` 和 `site/dist/` 都不进入 Git。
:::

## 写页面时

工程事实来自 Architecture、Spec、ADR、代码和测试。页面先用一个具体场景解释，再引入必要术语；
不要逐词翻译工程文档，也不要把未来路线写成当前功能。每页的 `bearStatus` 和 `sourceRefs` 用于
标记内容性质和事实来源。

完整关闭流程见[Feature 完成时怎样更新文档](../development/feature-documentation.md)。
