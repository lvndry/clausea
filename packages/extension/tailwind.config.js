/** @type {import('tailwindcss').Config} */
export default {
  content: ["./entrypoints/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Verdict colors
        safe: {
          DEFAULT: "#22c55e",
          light: "#dcfce7",
        },
        caution: {
          DEFAULT: "#f59e0b",
          light: "#fef3c7",
        },
        danger: {
          DEFAULT: "#ef4444",
          light: "#fee2e2",
        },
        // Brand
        brand: {
          DEFAULT: "#6366f1",
          light: "#e0e7ff",
        },
      },
    },
  },
  plugins: [],
};
