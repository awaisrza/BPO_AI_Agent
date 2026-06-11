import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#09090b",
          raised: "#0c0c0f",
          overlay: "#141419",
          border: "rgba(255, 255, 255, 0.08)",
        },
        accent: {
          DEFAULT: "#fafafa",
          muted: "#e4e4e7",
          soft: "rgba(255, 255, 255, 0.06)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      letterSpacing: {
        tightest: "-0.025em",
      },
    },
  },
  plugins: [],
};

export default config;
