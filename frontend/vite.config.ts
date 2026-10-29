import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // pasta própria para os arquivos do build (nomes com hash): /static/…
  build: { assetsDir: "static" },
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
