import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const originsdTarget = process.env.VITE_ORIGINSD_PROXY_TARGET ?? "http://127.0.0.1:48700";
const intelligenceTarget = process.env.VITE_ORIGINS_INTELLIGENCE_PROXY_TARGET ?? "http://127.0.0.1:48710";
const phase5Target = process.env.VITE_ORIGINS_PHASE5_PROXY_TARGET ?? "http://127.0.0.1:48720";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: {
      "/origins-api": {
        target: originsdTarget,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/origins-api/, ""),
      },
      "/origins-intelligence": {
        target: intelligenceTarget,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/origins-intelligence/, ""),
      },
      "/origins-phase5": {
        target: phase5Target,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/origins-phase5/, ""),
      },
    },
  },
});
