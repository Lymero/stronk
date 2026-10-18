import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte(), svelteTesting()],
  // MockBackend serves builds from fixtures/data, outside this package.
  server: { fs: { allow: ["../.."] }, host: "127.0.0.1", port: 5173, strictPort: true },
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"], include: ["src/**/*.test.ts"] },
});
