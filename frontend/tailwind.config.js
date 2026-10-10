/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f5f6f8",
        panel: "#ffffff",
        soft: "#f2f4f7",
        line: "#e6e8ec",
        ink: "#1f2937",
        muted: "#6b7280",
        brand: { 50: "#e9f9ef", 500: "#22c55e", 600: "#16a34a", 700: "#15803d" },
        danger: { 50: "#fdecec", 600: "#dc2626" },
        warn: { 50: "#fef3e2", 600: "#d97706" },
        info: { 50: "#e8f0fe", 600: "#2563eb" },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans Thai"', '"IBM Plex Sans Thai Fallback"', "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "Helvetica", "Arial", "sans-serif"],
      },
      boxShadow: { card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)" },
      borderRadius: { xl2: "14px" },
    },
  },
  plugins: [],
};
