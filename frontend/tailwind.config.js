/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // ArchPilot design tokens
        bg: {
          primary: "#0a0e1a",
          secondary: "#111827",
          tertiary: "#1a2234",
          elevated: "#1f2a3d",
        },
        accent: {
          blue: "#3b82f6",
          "blue-dim": "#1d4ed8",
          "blue-glow": "#60a5fa",
          green: "#10b981",
          red: "#ef4444",
          amber: "#f59e0b",
          purple: "#8b5cf6",
        },
        border: {
          subtle: "#1e2d45",
          DEFAULT: "#263354",
          strong: "#334d7a",
        },
        text: {
          primary: "#e2e8f0",
          secondary: "#94a3b8",
          muted: "#64748b",
          inverse: "#0a0e1a",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Cascadia Code", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        glow: "0 0 20px rgba(59, 130, 246, 0.15)",
        "glow-lg": "0 0 40px rgba(59, 130, 246, 0.25)",
      },
    },
  },
  plugins: [],
};
