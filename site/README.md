# BearAgent Docs

F-0015 提供的 Starlight 本地文档站。它同时维护面向初学者的 Agent 学习路径和面向贡献者的开发者文档；P1 期间只本地预览和构建，不部署服务器。

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

## Content contract

每个 Feature 关闭时都要更新：

1. `docs/` 中的工程事实；
2. `site/src/content/docs/zh-cn/learn/` 或相关初学者专题；
3. `site/src/content/docs/zh-cn/development/` 中的实现导读；
4. `site/src/content/docs/zh-cn/project/` 中的当前状态。

每个 P 阶段关闭时还要更新学习地图、开发者架构总结和里程碑结果。具体规则见
`/zh-cn/development/feature-documentation/`。
