import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const currentDir = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(currentDir, '..')

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, '')
  const port = env.BACKEND_PORT || '8001'
  const apiBase = env.VITE_API_BASE || `http://localhost:${port}`

  return {
    plugins: [react()],
    envDir: repoRoot,
    define: {
      'import.meta.env.VITE_API_BASE': JSON.stringify(apiBase),
    },
    build: {
      rollupOptions: {
        input: {
          app: path.resolve(currentDir, 'index.html'),
          'design-system-preview': path.resolve(currentDir, 'design-system-preview.html'),
        },
      },
    },
  }
})
