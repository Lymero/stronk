// The web build viewer (ADR-086): the same UI from viewer.html on `HttpBackend`, built apart from
// the desktop app's (vite.config.ts), which never needs the WebAssembly core.
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [svelte()],
  build: { outDir: "dist-viewer", rollupOptions: { input: "viewer.html" } },
  server: { host: "127.0.0.1", port: 5174, strictPort: true, open: false },
  preview: { host: "127.0.0.1", port: 5174, strictPort: true },
});
