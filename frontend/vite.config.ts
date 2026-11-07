import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development Vite plays the API gateway's role, using the same /api/<service> paths.
const services: Record<string, number> = { identity: 8001, catalog: 8002, orders: 8003, notifications: 8004, agent: 8005 };
const proxy = Object.fromEntries(
  Object.entries(services).map(([name, port]) => [
    `/api/${name}`,
    { target: `http://localhost:${port}`, ws: name === "notifications", rewrite: (p: string) => p.replace(`/api/${name}`, "") },
  ]),
);

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5173, proxy },
  build: {
    rollupOptions: {
      output: {
        manualChunks: { vendor: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"], mantine: ["@mantine/core", "@mantine/hooks"], charts: ["@mantine/charts", "recharts"] },
      },
    },
  },
});
