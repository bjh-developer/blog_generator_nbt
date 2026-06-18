import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // brand palette as semantic tokens (mix, not pure purple)
        cream: "#fff4de",
        ink: "#352757",
        purple: "#784eb5",
        lilac: "#cdc5fc",
        orchid: "#e2a9f1",
        pink: "#faaef1",
        bluebrand: "#5675f0",
        navy: "#0c3571",
        cyan: "#88e5f6",
        orange: "#ff914d",
        peach: "#ffb169",
      },
      fontFamily: {
        display: ["var(--font-atkinson)", "system-ui", "sans-serif"],
        body: ["var(--font-atkinson)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        pill: "9999px",
      },
    },
  },
  plugins: [],
};
export default config;
