import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';

export default defineConfig({
  integrations: [
    mermaid({
      autoTheme: true,
      enableLog: false,
      mermaidConfig: {
        securityLevel: 'strict',
        flowchart: { curve: 'basis' },
      },
    }),
    starlight({
      title: 'BearAgent Docs',
      description: '让个人 Agent 在本地可靠地完成长任务',
      defaultLocale: 'zh-cn',
      locales: {
        'zh-cn': {
          label: '简体中文',
          lang: 'zh-CN',
        },
      },
      lastUpdated: true,
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        {
          label: '开始',
          items: [
            { label: 'BearAgent 是什么', slug: 'start/what-is-bearagent' },
            { label: '产品定位', slug: 'project/positioning' },
          ],
        },
        {
          label: '学习 Agent',
          items: [
            { label: '学习路径', slug: 'learn' },
            { label: 'Agent 基础原理', slug: 'learn/agent-basics' },
            { label: 'Run 状态与预算', slug: 'learn/runtime-state-and-budgets' },
            { label: '模型 Provider 边界', slug: 'learn/model-provider-boundary' },
          ],
        },
        {
          label: 'BearAgent 架构',
          items: [
            { label: '架构概览', slug: 'architecture' },
            { label: 'F-0001：内部数据格式', slug: 'architecture/domain-contracts' },
          ],
        },
        {
          label: '开发者文档',
          items: [
            { label: '开发者入口', slug: 'development' },
            { label: 'Feature 文档同步', slug: 'development/feature-documentation' },
            { label: 'F-0001 实现导读', slug: 'development/domain-contracts' },
            { label: 'F-0002 实现导读', slug: 'development/run-reducer-and-budgets' },
            { label: 'F-0004 实现导读', slug: 'development/model-provider' },
          ],
        },
        {
          label: '指南',
          items: [
            { label: '本地运行文档站', slug: 'guides/local-docs' },
          ],
        },
        {
          label: '参考',
          items: [
            { label: '术语表', slug: 'reference/glossary' },
            { label: '资料来源', slug: 'reference/sources' },
          ],
        },
        {
          label: '项目',
          items: [
            { label: '当前实现状态', slug: 'project/status' },
            { label: '阶段与里程碑', slug: 'project/milestones' },
          ],
        },
      ],
    }),
  ],
});
