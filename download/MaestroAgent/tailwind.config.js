/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app.html", "./scripts/app-script.js"],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#06060d', 900: '#0e0e1a', 800: '#161624', 700: '#1e1e30', 600: '#262640',
        },
        brand: {
          violet: '#7c5cff', cyan: '#5cc8ff', amber: '#ffb84d', rose: '#ff5577',
          purple: '#a855f7', sky: '#38bdf8', green: '#00d4aa',
        },
        fg: {
          100: '#e4e4e7', 200: '#d4d4d8', 300: '#a1a1aa', 400: '#71717a',
          500: '#5c5c70', 600: '#3c3c4c',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
