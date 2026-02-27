/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'cinzel': ['Cinzel', 'serif'],
        'cormorant': ['Cormorant Garamond', 'serif'],
      },
      colors: {
        'parchment': '#faf8f3',
        'gold': '#d4af37',
        'midnight': '#1a1a2e',
      }
    },
  },
  plugins: [],
}
