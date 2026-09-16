// vite.config.ts
import { fileURLToPath, URL } from "node:url";
import react from "file:///sessions/hopeful-tender-mendel/mnt/projects/azure-ai-command-center/apps/web/node_modules/@vitejs/plugin-react/dist/index.js";
import { defineConfig } from "file:///sessions/hopeful-tender-mendel/mnt/projects/azure-ai-command-center/apps/web/node_modules/vite/dist/node/index.js";
var __vite_injected_original_import_meta_url = "file:///sessions/hopeful-tender-mendel/mnt/projects/azure-ai-command-center/apps/web/vite.config.ts";
var vite_config_default = defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", __vite_injected_original_import_meta_url)) }
  },
  server: {
    port: 5173,
    proxy: {
      // Dev-only proxy so the browser sees a single origin and CORS stays simple.
      "/api": { target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000", changeOrigin: true },
      "/health": { target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000", changeOrigin: true }
    }
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Recharts is the largest dependency by far; splitting it keeps the
        // initial bundle small for pages that render no charts.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          query: ["@tanstack/react-query"]
        }
      }
    }
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"]
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvaG9wZWZ1bC10ZW5kZXItbWVuZGVsL21udC9wcm9qZWN0cy9henVyZS1haS1jb21tYW5kLWNlbnRlci9hcHBzL3dlYlwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL3Nlc3Npb25zL2hvcGVmdWwtdGVuZGVyLW1lbmRlbC9tbnQvcHJvamVjdHMvYXp1cmUtYWktY29tbWFuZC1jZW50ZXIvYXBwcy93ZWIvdml0ZS5jb25maWcudHNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL3Nlc3Npb25zL2hvcGVmdWwtdGVuZGVyLW1lbmRlbC9tbnQvcHJvamVjdHMvYXp1cmUtYWktY29tbWFuZC1jZW50ZXIvYXBwcy93ZWIvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBmaWxlVVJMVG9QYXRoLCBVUkwgfSBmcm9tICdub2RlOnVybCdcblxuaW1wb3J0IHJlYWN0IGZyb20gJ0B2aXRlanMvcGx1Z2luLXJlYWN0J1xuaW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcblxuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgcGx1Z2luczogW3JlYWN0KCldLFxuICByZXNvbHZlOiB7XG4gICAgYWxpYXM6IHsgJ0AnOiBmaWxlVVJMVG9QYXRoKG5ldyBVUkwoJy4vc3JjJywgaW1wb3J0Lm1ldGEudXJsKSkgfSxcbiAgfSxcbiAgc2VydmVyOiB7XG4gICAgcG9ydDogNTE3MyxcbiAgICBwcm94eToge1xuICAgICAgLy8gRGV2LW9ubHkgcHJveHkgc28gdGhlIGJyb3dzZXIgc2VlcyBhIHNpbmdsZSBvcmlnaW4gYW5kIENPUlMgc3RheXMgc2ltcGxlLlxuICAgICAgJy9hcGknOiB7IHRhcmdldDogcHJvY2Vzcy5lbnYuVklURV9BUElfQkFTRV9VUkwgPz8gJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCcsIGNoYW5nZU9yaWdpbjogdHJ1ZSB9LFxuICAgICAgJy9oZWFsdGgnOiB7IHRhcmdldDogcHJvY2Vzcy5lbnYuVklURV9BUElfQkFTRV9VUkwgPz8gJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCcsIGNoYW5nZU9yaWdpbjogdHJ1ZSB9LFxuICAgIH0sXG4gIH0sXG4gIGJ1aWxkOiB7XG4gICAgb3V0RGlyOiAnZGlzdCcsXG4gICAgc291cmNlbWFwOiB0cnVlLFxuICAgIHJvbGx1cE9wdGlvbnM6IHtcbiAgICAgIG91dHB1dDoge1xuICAgICAgICAvLyBSZWNoYXJ0cyBpcyB0aGUgbGFyZ2VzdCBkZXBlbmRlbmN5IGJ5IGZhcjsgc3BsaXR0aW5nIGl0IGtlZXBzIHRoZVxuICAgICAgICAvLyBpbml0aWFsIGJ1bmRsZSBzbWFsbCBmb3IgcGFnZXMgdGhhdCByZW5kZXIgbm8gY2hhcnRzLlxuICAgICAgICBtYW51YWxDaHVua3M6IHtcbiAgICAgICAgICByZWFjdDogWydyZWFjdCcsICdyZWFjdC1kb20nLCAncmVhY3Qtcm91dGVyLWRvbSddLFxuICAgICAgICAgIGNoYXJ0czogWydyZWNoYXJ0cyddLFxuICAgICAgICAgIHF1ZXJ5OiBbJ0B0YW5zdGFjay9yZWFjdC1xdWVyeSddLFxuICAgICAgICB9LFxuICAgICAgfSxcbiAgICB9LFxuICB9LFxuICB0ZXN0OiB7XG4gICAgZW52aXJvbm1lbnQ6ICdqc2RvbScsXG4gICAgZ2xvYmFsczogdHJ1ZSxcbiAgICBzZXR1cEZpbGVzOiBbJy4vc3JjL3Rlc3Qvc2V0dXAudHMnXSxcbiAgICBpbmNsdWRlOiBbJ3NyYy8qKi8qLnRlc3Que3RzLHRzeH0nXSxcbiAgfSxcbn0pXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQXlaLFNBQVMsZUFBZSxXQUFXO0FBRTViLE9BQU8sV0FBVztBQUNsQixTQUFTLG9CQUFvQjtBQUhxTyxJQUFNLDJDQUEyQztBQUtuVCxJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsTUFBTSxDQUFDO0FBQUEsRUFDakIsU0FBUztBQUFBLElBQ1AsT0FBTyxFQUFFLEtBQUssY0FBYyxJQUFJLElBQUksU0FBUyx3Q0FBZSxDQUFDLEVBQUU7QUFBQSxFQUNqRTtBQUFBLEVBQ0EsUUFBUTtBQUFBLElBQ04sTUFBTTtBQUFBLElBQ04sT0FBTztBQUFBO0FBQUEsTUFFTCxRQUFRLEVBQUUsUUFBUSxRQUFRLElBQUkscUJBQXFCLHlCQUF5QixjQUFjLEtBQUs7QUFBQSxNQUMvRixXQUFXLEVBQUUsUUFBUSxRQUFRLElBQUkscUJBQXFCLHlCQUF5QixjQUFjLEtBQUs7QUFBQSxJQUNwRztBQUFBLEVBQ0Y7QUFBQSxFQUNBLE9BQU87QUFBQSxJQUNMLFFBQVE7QUFBQSxJQUNSLFdBQVc7QUFBQSxJQUNYLGVBQWU7QUFBQSxNQUNiLFFBQVE7QUFBQTtBQUFBO0FBQUEsUUFHTixjQUFjO0FBQUEsVUFDWixPQUFPLENBQUMsU0FBUyxhQUFhLGtCQUFrQjtBQUFBLFVBQ2hELFFBQVEsQ0FBQyxVQUFVO0FBQUEsVUFDbkIsT0FBTyxDQUFDLHVCQUF1QjtBQUFBLFFBQ2pDO0FBQUEsTUFDRjtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQUEsRUFDQSxNQUFNO0FBQUEsSUFDSixhQUFhO0FBQUEsSUFDYixTQUFTO0FBQUEsSUFDVCxZQUFZLENBQUMscUJBQXFCO0FBQUEsSUFDbEMsU0FBUyxDQUFDLHdCQUF3QjtBQUFBLEVBQ3BDO0FBQ0YsQ0FBQzsiLAogICJuYW1lcyI6IFtdCn0K
