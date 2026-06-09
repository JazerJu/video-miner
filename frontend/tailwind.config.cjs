// tailwind.config.cjs
module.exports = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#54CACA', //  bg-primary      bg-primary/10  bg-primary/50 ...
        'primary-dark': '#3EB5B5',
        secondary: '#ACD2D3',
        accent: '#6896A2',
        textmain: '#24373B',
        background: '#F5F7FA',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
