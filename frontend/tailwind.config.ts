import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#1e3a8a",
          fg: "#0f172a",
          muted: "#64748b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
