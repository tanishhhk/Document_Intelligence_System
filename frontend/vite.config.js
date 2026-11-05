import process from 'node:process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE is the path the site is served from, e.g. /Document_Intelligence_System/ on GitHub Pages.
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
})
