import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [vue(), UnoCSS()],
  base: '/gba-narutorpg-chs/',
  build: {
    outDir: resolve(__dirname, '../pages'),
    emptyOutDir: true,
  },
})
