/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        apple: {
          bg: '#FFFFFF',
          'bg-secondary': '#F5F5F7',
          text: '#1D1D1F',
          'text-secondary': '#86868B',
          border: '#E5E5E5',
          blue: '#007AFF',
          disabled: '#C7C7CC',
          'scrollbar': '#D1D1D6',
          'scrollbar-hover': '#A1A1A6',
        },
        user: {
          avatar: '#FF6B6B',
          'avatar-end': '#FFA07A',
        },
      },
      fontFamily: {
        apple: ['-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Helvetica Neue', 'sans-serif'],
      },
      borderRadius: {
        'apple': '12px',
        'pill': '20px',
      },
      boxShadow: {
        'apple-card': '0 1px 3px rgba(0,0,0,0.1)',
        'apple-drawer': '0 0 20px rgba(0,0,0,0.1)',
        'apple-picker': '0 4px 20px rgba(0,0,0,0.15)',
      },
      animation: {
        /* iOS 风格进入动画 - 快速响应，平滑减速 */
        'drawer-slide': 'drawerSlide 350ms cubic-bezier(0.32, 0.72, 0, 1)',
        'fade-in': 'fadeIn 350ms cubic-bezier(0.32, 0.72, 0, 1)',
        'message-appear': 'messageAppear 400ms cubic-bezier(0.32, 0.72, 0, 1)',
        /* iOS 风格退出动画 - 加速曲线 */
        'fade-out': 'fadeOut 250ms cubic-bezier(0.36, 0, 0.66, -0.56)',
        'drawer-slide-out': 'drawerSlideOut 250ms cubic-bezier(0.36, 0, 0.66, -0.56)',
        /* 弹性动画 */
        'bounce-ios': 'bounceIOS 500ms cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      keyframes: {
        /* 抽屉滑入 */
        drawerSlide: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        /* 抽屉滑出 */
        drawerSlideOut: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-100%)' },
        },
        /* 淡入 - 带轻微上移和缩放 */
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(8px) scale(0.98)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        /* 淡出 - 带轻微下移和缩放 */
        fadeOut: {
          '0%': { opacity: '1', transform: 'translateY(0) scale(1)' },
          '100%': { opacity: '0', transform: 'translateY(16px) scale(0.95)' },
        },
        /* 消息出现 - 更明显的弹性 */
        messageAppear: {
          '0%': { opacity: '0', transform: 'translateY(16px) scale(0.95)' },
          '60%': { transform: 'translateY(-2px) scale(1.01)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        /* iOS 弹性反弹 */
        bounceIOS: {
          '0%': { transform: 'scale(0.95)' },
          '50%': { transform: 'scale(1.02)' },
          '100%': { transform: 'scale(1)' },
        },
      },
      transitionTimingFunction: {
        'ios-enter': 'cubic-bezier(0.32, 0.72, 0, 1)',
        'ios-exit': 'cubic-bezier(0.36, 0, 0.66, -0.56)',
        'ios-spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
        'ios-smooth': 'cubic-bezier(0.25, 0.1, 0.25, 1)',
      },
      transitionDuration: {
        '85': '85ms',
        '120': '120ms',
        '180': '180ms',
        '350': '350ms',
        '400': '400ms',
      },
      zIndex: {
        'drawer-overlay': '20',
        'drawer': '30',
        'picker': '40',
      },
    },
  },
  plugins: [],
}