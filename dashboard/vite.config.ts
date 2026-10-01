import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Relative base + hash routing: the build works from any sub-path (GitHub Pages project sites).
export default defineConfig({
  base: "./",
  plugins: [svelte()],
  build: { target: "es2022", chunkSizeWarningLimit: 600 },
  test: { environment: "node" },
});
