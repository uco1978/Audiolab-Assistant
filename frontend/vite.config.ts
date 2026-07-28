import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:8001",
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 5174,
    allowedHosts: ["ppc-frontend.onrender.com", ".onrender.com"],
  },
});
