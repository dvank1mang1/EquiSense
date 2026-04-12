/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#ecfeff",
          100: "#cffafe",
          200: "#a5f3fc",
          300: "#67e8f9",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
          700: "#0e7490",
          800: "#155e75",
          900: "#164e63",
        },
        accent: {
          DEFAULT: "#34d399",
          muted: "#6ee7b7",
          dim: "rgba(52, 211, 153, 0.12)",
        },
        surface: {
          950: "#030712",
          900: "#0b1220",
          850: "#0f172a",
          800: "#151f32",
          750: "#1a2740",
          700: "#243049",
          600: "#334155",
          500: "#475569",
        },
        success: "#34d399",
        danger: "#f87171",
        warning: "#fbbf24",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        "display": ["2.25rem", { lineHeight: "2.5rem", letterSpacing: "-0.025em", fontWeight: "700" }],
      },
      boxShadow: {
        "glow-sm": "0 0 24px -8px rgba(6, 182, 212, 0.35)",
        "glow-md": "0 0 40px -12px rgba(6, 182, 212, 0.25)",
        "card": "0 1px 0 0 rgba(255, 255, 255, 0.04) inset, 0 8px 32px -12px rgba(0, 0, 0, 0.45)",
        "card-hover": "0 1px 0 0 rgba(255, 255, 255, 0.06) inset, 0 12px 40px -10px rgba(0, 0, 0, 0.5)",
        "nav": "0 1px 0 0 rgba(255, 255, 255, 0.06)",
      },
      transitionDuration: {
        DEFAULT: "200ms",
        250: "250ms",
        350: "350ms",
      },
      transitionTimingFunction: {
        DEFAULT: "cubic-bezier(0.22, 1, 0.36, 1)",
        "out-soft": "cubic-bezier(0.33, 1, 0.68, 1)",
      },
      backgroundImage: {
        "mesh-gradient":
          "radial-gradient(ellipse 90% 55% at 50% -15%, rgba(6, 182, 212, 0.14), transparent 52%), radial-gradient(ellipse 70% 45% at 100% 0%, rgba(52, 211, 153, 0.06), transparent 45%), radial-gradient(ellipse 55% 40% at 0% 25%, rgba(8, 145, 178, 0.08), transparent 50%)",
      },
    },
  },
  plugins: [],
};
