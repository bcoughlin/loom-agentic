import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/**
 * Library build target — produces a consumable ESM bundle in dist-lib/
 * for other React projects to import. Distinct from vite.config.js
 * which builds the standalone SPA into dist/ for serve.py to mount.
 *
 * Run with:
 *   npm run build:lib
 *
 * Output:
 *   dist-lib/loom-web.js     — ESM entry
 *   dist-lib/loom-web.css    — extracted styles (currently minimal —
 *                               components use inline styles, so this is
 *                               only the global resets from index.css)
 *
 * Externalised deps (peer dependencies — consumers provide them):
 *   react, react-dom, react/jsx-runtime, react-router-dom, mermaid
 *
 * Why externalise: bundling them would balloon size AND risk multiple
 * react instances in consumer apps (which breaks hooks). Standard
 * library-mode practice.
 */
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-lib',
    emptyOutDir: true,
    lib: {
      entry: resolve(__dirname, 'src/index.js'),
      formats: ['es'],
      fileName: () => 'loom-web.js',
    },
    rollupOptions: {
      external: [
        'react',
        'react-dom',
        'react/jsx-runtime',
        'react-router-dom',
        'mermaid',
      ],
    },
    sourcemap: true,
    minify: false,  // libraries publish readable source; consumer's bundler minifies
  },
})
