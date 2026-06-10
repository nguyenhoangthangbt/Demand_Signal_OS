import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// DSO web is a thin v0.1 preview SPA. It does not own a backend API
// (DSO is library-first per CONSTITUTION L2); it talks to the
// Plan2Cash router for the synthetic forecast preview.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5176,
  },
});
