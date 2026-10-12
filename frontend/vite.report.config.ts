import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    define: { 'process.env.NODE_ENV': JSON.stringify('production') },
    build: {
        outDir: 'dist-report',
        lib: { entry: 'src/report/main.tsx', name: 'WaveCatcherReport', formats: ['iife'], fileName: () => 'report.js', cssFileName: 'report' },
        cssCodeSplit: false,
        rollupOptions: { output: { inlineDynamicImports: true } },
    },
});
