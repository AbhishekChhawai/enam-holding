import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

declare const process: { env: Record<string, string | undefined> };

// VITE_DEMO=1 builds the phone demo: one self-contained HTML file with the in-browser data layer.
// Normal builds alias the demo module to a stub, so no demo code or data ships to production.
const demo = process.env.VITE_DEMO === "1";
const stub = fileURLToPath(new URL("./src/demo/stub.ts", import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(demo ? [viteSingleFile()] : [])],
  resolve: { alias: demo ? [] : [{ find: /^\.\/demo\/mock$/, replacement: stub }] },
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: demo ? "dist-demo" : "dist", sourcemap: false },
});
