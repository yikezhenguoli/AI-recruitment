/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0f2740',
        muted: '#5b7693',
        line: '#e1ebf4',
        brand: {
          DEFAULT: '#2f89d8',
          deep: '#1c5f9c',
          soft: '#eaf4fe',
        },
        jade: {
          DEFAULT: '#12a39b',
          deep: '#0b7a74',
          soft: '#e6f7f5',
        },
      },
      boxShadow: {
        card: '0 24px 60px -32px rgba(15, 39, 64, 0.35)',
        soft: '0 12px 32px -20px rgba(15, 39, 64, 0.30)',
        float: '0 18px 40px -18px rgba(28, 95, 156, 0.45)',
      },
      fontFamily: {
        sans: [
          'Inter',
          'PingFang SC',
          'Hiragino Sans GB',
          'Microsoft YaHei',
          'Noto Sans SC',
          'system-ui',
          'sans-serif',
        ],
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        breathe: {
          '0%, 100%': { transform: 'scale(1)', opacity: '.55' },
          '50%': { transform: 'scale(1.06)', opacity: '.85' },
        },
      },
      animation: {
        'fade-up': 'fade-up .45s ease-out both',
        breathe: 'breathe 9s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
