import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": process.env.FALSIFY_API_PROXY ?? "http://127.0.0.1:8000",
      "/health": process.env.FALSIFY_API_PROXY ?? "http://127.0.0.1:8000",
      "/help": process.env.FALSIFY_API_PROXY ?? "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
