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
            { label: 'BearAgent 要解决什么问题', slug: 'start/what-is-bearagent' },
            { label: '为什么做 BearAgent', slug: 'project/positioning' },
          ],
        },
        {
          label: '学习 Agent',
          items: [
            { label: '从一次任务理解 BearAgent', slug: 'learn' },
            { label: '一项 Agent 任务怎样运转', slug: 'learn/agent-basics' },
            { label: '状态和预算怎样计算', slug: 'learn/runtime-state-and-budgets' },
            { label: '逐条读懂一次 Run', slug: 'learn/run-event-reducer-walkthrough' },
            { label: '持久事实与安全恢复', slug: 'learn/durable-events' },
            { label: '为什么模型需要独立边界', slug: 'learn/model-provider-boundary' },
            { label: 'Tool 请求为什么要过四道检查', slug: 'learn/tool-execution-boundary' },
            { label: 'Windows 和 Unix 路径怎样统一', slug: 'learn/workspace-read-boundary' },
            { label: '一次文件任务怎样走完整条链', slug: 'learn/agent-loop-file-task' },
          ],
        },
        {
          label: 'BearAgent 架构',
          items: [
            { label: 'Runtime 各部分怎样协作', slug: 'architecture' },
            { label: '内部怎样交换数据', slug: 'architecture/domain-contracts' },
          ],
        },
        {
          label: '开发者文档',
          items: [
            { label: '从哪里开始读代码', slug: 'development' },
            { label: 'Feature 怎样更新文档', slug: 'development/feature-documentation' },
            { label: 'F-0001：修改内部数据', slug: 'development/domain-contracts' },
            { label: 'F-0002：修改状态和预算', slug: 'development/run-reducer-and-budgets' },
            { label: 'F-0003：SQLite EventStore', slug: 'development/sqlite-event-store' },
            { label: 'F-0004：ModelProvider', slug: 'development/model-provider' },
            { label: 'F-0006：Tool 执行边界', slug: 'development/tool-execution-boundary' },
            { label: 'F-0007：workspace 只读 Tool', slug: 'development/workspace-read-tools' },
            { label: 'F-0008：原子输出与 Artifact', slug: 'development/atomic-output-artifacts' },
            { label: 'F-0016：有界 Agent Loop', slug: 'development/agent-loop' },
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
            { label: '参考资料怎样使用', slug: 'reference/sources' },
          ],
        },
        {
          label: '项目',
          items: [
            { label: '现在实现到了哪里', slug: 'project/status' },
            { label: 'BearAgent 按什么顺序完成', slug: 'project/milestones' },
          ],
        },
      ],
    }),
  ],
});
