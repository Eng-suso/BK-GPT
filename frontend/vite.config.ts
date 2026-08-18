import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
