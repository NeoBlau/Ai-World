import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#05060a", 900: "#0a0c12", 850: "#0e1118", 800: "#131722", 700: "#1b2030" },
        mist: { 100: "#eef1f8", 300: "#b9c0d4", 400: "#8c94ab", 500: "#646c84" },
        accent: { DEFAULT: "#8b9cff", violet: "#b18cff", cyan: "#5ee6f0", rose: "#ff8fb3", amber: "#ffc876", mint: "#6ff0b8" },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Display", "Inter", "Segoe UI", "Roboto", "Helvetica Neue", "sans-serif"],
        mono: ["SF Mono", "JetBrains Mono", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        glass: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 20px 50px -20px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(139,156,255,0.25), 0 8px 40px -8px rgba(139,156,255,0.35)",
      },
      keyframes: {
        "fade-up": { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        pulse2: { "0%,100%": { opacity: "1" }, "50%": { opacity: ".35" } },
        drift: { "0%,100%": { transform: "translate(0,0)" }, "50%": { transform: "translate(2%, -3%)" } },
      },
      animation: {
        "fade-up": "fade-up .45s cubic-bezier(.2,.7,.2,1) both",
        pulse2: "pulse2 2.2s ease-in-out infinite",
        drift: "drift 18s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
