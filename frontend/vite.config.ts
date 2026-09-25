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
  server: {
    // Le schermate sono caricate a richiesta (`src/app/screens.tsx`): in
    // produzione e' il punto, in sviluppo significa che il dev server compila
    // il modulo alla prima navigazione. Con piu' schede aperte insieme - i
    // worker di Playwright - le compilazioni si mettono in coda e la prima
    // apertura di ogni sezione scade. Qui il server se le prepara all'avvio,
    // quando non sta aspettando nessuno.
    warmup: {
      clientFiles: ["./src/app/screens.tsx", "./src/main.tsx"],
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
