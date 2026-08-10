import { defineCollection } from 'astro:content';
import { z } from 'astro/zod';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        bearStatus: z.enum(['concept', 'design', 'implemented', 'planned', 'mixed']),
        sourceRefs: z.array(z.string()).default([]),
      }),
    }),
  }),
};
