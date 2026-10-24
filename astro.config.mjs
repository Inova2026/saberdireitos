// @ts-check
import { defineConfig } from "astro/config";

import tailwindcss from "@tailwindcss/vite";

import mdx from "@astrojs/mdx";

import sitemap from "@astrojs/sitemap";

// https://astro.build/config
export default defineConfig({
  site: "[https://saberdireitos.com.br](https://saberdireitos.com.br)",
  vite: {
    plugins: [tailwindcss()],
  },

  integrations: [mdx(), sitemap()],
});
