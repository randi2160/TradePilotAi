/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 500: '#00d4aa', 600: '#00b894' },
        dark:  { 900: '#0a0e1a', 800: '#111827', 700: '#1f2937', 600: '#374151' },
      },
    },
  },
  plugins: [],
}
