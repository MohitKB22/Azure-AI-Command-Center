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
  build: { outDir: "dist", sourcemap: true },
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
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvaG9wZWZ1bC10ZW5kZXItbWVuZGVsL21udC9wcm9qZWN0cy9henVyZS1haS1jb21tYW5kLWNlbnRlci9hcHBzL3dlYlwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL3Nlc3Npb25zL2hvcGVmdWwtdGVuZGVyLW1lbmRlbC9tbnQvcHJvamVjdHMvYXp1cmUtYWktY29tbWFuZC1jZW50ZXIvYXBwcy93ZWIvdml0ZS5jb25maWcudHNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL3Nlc3Npb25zL2hvcGVmdWwtdGVuZGVyLW1lbmRlbC9tbnQvcHJvamVjdHMvYXp1cmUtYWktY29tbWFuZC1jZW50ZXIvYXBwcy93ZWIvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBmaWxlVVJMVG9QYXRoLCBVUkwgfSBmcm9tICdub2RlOnVybCdcblxuaW1wb3J0IHJlYWN0IGZyb20gJ0B2aXRlanMvcGx1Z2luLXJlYWN0J1xuaW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcblxuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgcGx1Z2luczogW3JlYWN0KCldLFxuICByZXNvbHZlOiB7XG4gICAgYWxpYXM6IHsgJ0AnOiBmaWxlVVJMVG9QYXRoKG5ldyBVUkwoJy4vc3JjJywgaW1wb3J0Lm1ldGEudXJsKSkgfSxcbiAgfSxcbiAgc2VydmVyOiB7XG4gICAgcG9ydDogNTE3MyxcbiAgICBwcm94eToge1xuICAgICAgLy8gRGV2LW9ubHkgcHJveHkgc28gdGhlIGJyb3dzZXIgc2VlcyBhIHNpbmdsZSBvcmlnaW4gYW5kIENPUlMgc3RheXMgc2ltcGxlLlxuICAgICAgJy9hcGknOiB7IHRhcmdldDogcHJvY2Vzcy5lbnYuVklURV9BUElfQkFTRV9VUkwgPz8gJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCcsIGNoYW5nZU9yaWdpbjogdHJ1ZSB9LFxuICAgICAgJy9oZWFsdGgnOiB7IHRhcmdldDogcHJvY2Vzcy5lbnYuVklURV9BUElfQkFTRV9VUkwgPz8gJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCcsIGNoYW5nZU9yaWdpbjogdHJ1ZSB9LFxuICAgIH0sXG4gIH0sXG4gIGJ1aWxkOiB7IG91dERpcjogJ2Rpc3QnLCBzb3VyY2VtYXA6IHRydWUgfSxcbiAgdGVzdDoge1xuICAgIGVudmlyb25tZW50OiAnanNkb20nLFxuICAgIGdsb2JhbHM6IHRydWUsXG4gICAgc2V0dXBGaWxlczogWycuL3NyYy90ZXN0L3NldHVwLnRzJ10sXG4gICAgaW5jbHVkZTogWydzcmMvKiovKi50ZXN0Lnt0cyx0c3h9J10sXG4gIH0sXG59KVxuIl0sCiAgIm1hcHBpbmdzIjogIjtBQUF5WixTQUFTLGVBQWUsV0FBVztBQUU1YixPQUFPLFdBQVc7QUFDbEIsU0FBUyxvQkFBb0I7QUFIcU8sSUFBTSwyQ0FBMkM7QUFLblQsSUFBTyxzQkFBUSxhQUFhO0FBQUEsRUFDMUIsU0FBUyxDQUFDLE1BQU0sQ0FBQztBQUFBLEVBQ2pCLFNBQVM7QUFBQSxJQUNQLE9BQU8sRUFBRSxLQUFLLGNBQWMsSUFBSSxJQUFJLFNBQVMsd0NBQWUsQ0FBQyxFQUFFO0FBQUEsRUFDakU7QUFBQSxFQUNBLFFBQVE7QUFBQSxJQUNOLE1BQU07QUFBQSxJQUNOLE9BQU87QUFBQTtBQUFBLE1BRUwsUUFBUSxFQUFFLFFBQVEsUUFBUSxJQUFJLHFCQUFxQix5QkFBeUIsY0FBYyxLQUFLO0FBQUEsTUFDL0YsV0FBVyxFQUFFLFFBQVEsUUFBUSxJQUFJLHFCQUFxQix5QkFBeUIsY0FBYyxLQUFLO0FBQUEsSUFDcEc7QUFBQSxFQUNGO0FBQUEsRUFDQSxPQUFPLEVBQUUsUUFBUSxRQUFRLFdBQVcsS0FBSztBQUFBLEVBQ3pDLE1BQU07QUFBQSxJQUNKLGFBQWE7QUFBQSxJQUNiLFNBQVM7QUFBQSxJQUNULFlBQVksQ0FBQyxxQkFBcUI7QUFBQSxJQUNsQyxTQUFTLENBQUMsd0JBQXdCO0FBQUEsRUFDcEM7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
