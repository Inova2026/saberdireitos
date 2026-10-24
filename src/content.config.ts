import { glob } from "astro/loaders";
import { defineCollection, z } from "astro:content";

const blog = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/blog" }),
  schema: z.object({
    title: z.string(),
    date: z.string(),
    category: z.string(),
    image: z.string(),
    excerpt: z.string(),
    description: z.string().optional(),
    geo_region: z.string().optional(),
  }),
});

export const collections = { blog };
