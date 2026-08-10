# BearAgent Docs

F-0015 提供的 Starlight 本地文档站。P1 期间只本地预览和构建，不部署服务器。

## Prerequisites

- Node.js 22.12 或更新版本
- npm 9.6.5 或更新版本

## Local commands

在仓库根目录执行：

```powershell
npm --prefix=site ci
npm run dev --prefix=site
```

开发服务器启动后访问 `http://localhost:4321/zh-cn/`。

验证生产构建和本地搜索：

```powershell
npm run build --prefix=site
npm run preview --prefix=site
```

构建输出位于 `site/dist/`，它是可重新生成的本地文件，不提交 Git。
