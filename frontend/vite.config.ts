import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  optimizeDeps: {
    include: [
      "bpmn-js/lib/Modeler",
      "bpmn-js-token-simulation",
    ],
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
