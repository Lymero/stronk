import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";
import { defineConfig } from "vitest/config";

declare const process: { env: Record<string, string | undefined> }; // Node's, without @types/node

export default defineConfig({
  plugins: [svelte(), svelteTesting()],
  server: {
    // MockBackend serves builds from fixtures/data, outside this package.
    fs: { allow: ["../.."] },
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    // CoreBackend (`?backend=core`): tools/lcu_mock/core_bridge.py, started by `just e2e`.
    proxy: {
      "/core": {
        target: process.env.STRONK_CORE_BRIDGE ?? "http://127.0.0.1:8790",
        rewrite: (path) => path.replace(/^\/core/, ""),
      },
    },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"], include: ["src/**/*.test.ts"] },
});
