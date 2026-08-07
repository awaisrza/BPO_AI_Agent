import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}", "./.claude-design/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "var(--bg-base)",
          raised: "var(--bg-raised)",
          overlay: "var(--bg-overlay)",
          border: "var(--border-default)",
          "border-subtle": "var(--border-subtle)",
        },
        foreground: {
          DEFAULT: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
          faint: "var(--text-faint)",
        },
        brand: {
          DEFAULT: "var(--brand)",
          hover: "var(--brand-hover)",
          muted: "var(--brand-muted)",
          foreground: "var(--brand-foreground)",
        },
        status: {
          success: "var(--status-success)",
          "success-muted": "var(--status-success-muted)",
          warning: "var(--status-warning)",
          "warning-muted": "var(--status-warning-muted)",
          danger: "var(--status-danger)",
          "danger-muted": "var(--status-danger-muted)",
          info: "var(--status-info)",
          "info-muted": "var(--status-info-muted)",
        },
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        DEFAULT: "var(--radius-md)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        caption: ["0.75rem", { lineHeight: "1rem" }],
        body: ["0.875rem", { lineHeight: "1.25rem" }],
      },
      spacing: {
        4.5: "1.125rem",
        13: "3.25rem",
        15: "3.75rem",
        18: "4.5rem",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        focus: "var(--shadow-focus)",
      },
      maxWidth: {
        content: "72rem",
      },
    },
  },
  plugins: [],
};

export default config;
