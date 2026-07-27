import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)", xl: "16px", "2xl": "20px", "3xl": "24px" },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "-apple-system", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontSize: { "2xs": ["0.625rem", { lineHeight: "0.875rem" }] },
      spacing: { 4.5: "1.125rem", 13: "3.25rem", 15: "3.75rem", 18: "4.5rem" },
      animation: {
        "fade-in": "fadeIn 0.5s cubic-bezier(0.16,1,0.3,1) forwards",
        "slide-up": "slideUp 0.5s cubic-bezier(0.16,1,0.3,1) forwards",
        "slide-down": "slideDown 0.4s cubic-bezier(0.16,1,0.3,1) forwards",
        "scale-in": "scaleIn 0.3s cubic-bezier(0.16,1,0.3,1) forwards",
        "shimmer": "shimmer 2s linear infinite",
        "pulse-slow": "pulse 4s cubic-bezier(0.4,0,0.6,1) infinite",
        "spin-slow": "spin 8s linear infinite",
        "counter": "fadeIn 0.8s ease-out forwards",
        "gradient": "gradient 6s ease infinite",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { opacity: "0", transform: "translateY(16px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        slideDown: { from: { opacity: "0", transform: "translateY(-8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        scaleIn: { from: { opacity: "0", transform: "scale(0.95)" }, to: { opacity: "1", transform: "scale(1)" } },
        shimmer: { from: { backgroundPosition: "-200% 0" }, to: { backgroundPosition: "200% 0" } },
        gradient: { "0%,100%": { backgroundPosition: "0% 50%" }, "50%": { backgroundPosition: "100% 50%" } },
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "dot-pattern": "radial-gradient(circle, hsl(var(--border)) 1px, transparent 1px)",
      },
      backgroundSize: { "dot-sm": "20px 20px", "dot-md": "32px 32px" },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
