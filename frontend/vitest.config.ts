import path from "node:path";
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    // I cinque secondi di default sono tarati su un test alla volta su una
    // macchina scarica. Qui girano ventisette file in parallelo, ognuno con il
    // proprio jsdom, e il test piu' lento del gruppo - un dialog controllato in
    // cui si digita una frase intera - passa da 1,3s da solo a oltre 5s quando
    // il resto della suite (o la suite Python) occupa la macchina. Falliva li',
    // e il rosso diceva "il form non salva" mentre il form salvava: era finito
    // il tempo, non rotto il comportamento.
    //
    // Alzare il tetto non indebolisce nessuna asserzione: il budget di attesa
    // non e' cio' che questi test verificano. Un test che ci mette davvero
    // quindici secondi sta segnalando un problema vero, e allora si guarda.
    testTimeout: 15_000,
    hookTimeout: 15_000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'dist/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/main.tsx',
      ],
    },
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'dist', 'e2e'],
  },
});
