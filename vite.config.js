import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/vis-network/")) return "network";
          if (id.includes("/node_modules/vis-data/")) return "network-data";
          if (id.includes("/node_modules/vis-util/")) return "network-utils";
          if (id.includes("/node_modules/chart.js/") || id.includes("/node_modules/@kurkle/")) {
            return "charts";
          }
          if (id.includes("/node_modules/lucide-react/")) return "icons";
          if (id.includes("/node_modules/react/") || id.includes("/node_modules/scheduler/")) {
            return "react-vendor";
          }
        },
      },
    },
  },
});
