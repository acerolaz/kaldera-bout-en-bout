/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    strictPort: true,
    // API FastAPI (make api) : même origine pour le navigateur, pas de CORS
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (chemin) => chemin.replace(/^\/api/, ""),
        // flux SSE : si l'API meurt en cours de route, couper aussi la connexion du navigateur
        // (sinon il ne voit ni erreur ni fin et ne se reconnecte jamais)
        configure: (proxy) =>
          proxy.on("proxyRes", (proxyRes, _req, res) =>
            proxyRes.on("close", () => {
              if (!res.writableEnded) res.destroy();
            }),
          ),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
