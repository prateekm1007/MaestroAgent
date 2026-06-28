import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './stories/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#070710', 900: '#0a0a14', 850: '#0e0e1a',
          800: '#12121e', 750: '#161624', 700: '#1c1c2c', 650: '#222234', 600: '#2a2a3c',
        },
        brand: {
          purple: '#7c5cff', purple2: '#6b4df5',
          cyan: '#00d4aa', cyan2: '#00b894',
          amber: '#ffb84d', rose: '#ff5577', sky: '#5cc8ff',
        },
        fg: {
          100: '#f4f4fc', 200: '#e8e8f0', 300: '#c8c8d8',
          400: '#8888a0', 500: '#5a5a72', 600: '#3a3a4a',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
