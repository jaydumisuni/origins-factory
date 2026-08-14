import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = process.env.VITE_ORIGINSD_PROXY_TARGET ?? "http://127.0.0.1:48700";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: {
      "/origins-api": {
        target,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/origins-api/, ""),
      },
    },
  },
});
