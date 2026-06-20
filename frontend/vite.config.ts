import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      // Proxy API requests to the FastAPI backend during development
      "/repositories": {
        target: "https://arch-pilot.onrender.com/",
        changeOrigin: true,
      },
      "/health": {
        target: "https://arch-pilot.onrender.com/",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom"],
          reactflow: ["reactflow"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
});
