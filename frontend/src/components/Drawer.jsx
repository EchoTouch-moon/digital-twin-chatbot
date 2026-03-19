import React, { useEffect, useState, useRef } from 'react';

/**
 * 可复用抽屉组件 - 液态玻璃风格，丝滑关闭动画
 */
const Drawer = ({ isOpen, onClose, children, width = 320 }) => {
  const [shouldRender, setShouldRender] = useState(false);
  const [shouldAnimate, setShouldAnimate] = useState(false);
  const closeTimeoutRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      // 打开：先渲染，下一帧开始动画
      setShouldRender(true);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setShouldAnimate(true);
        });
      });
      document.body.style.overflow = 'hidden';
    } else if (shouldRender) {
      // 关闭：播放关闭动画
      setShouldAnimate(false);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  const handleTransitionEnd = (e) => {
    // 只在关闭动画结束时触发
    if (!shouldAnimate && e.propertyName === 'transform') {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current);
      }
      closeTimeoutRef.current = setTimeout(() => {
        setShouldRender(false);
        document.body.style.overflow = '';
      }, 50);
    }
  };

  if (!shouldRender) return null;

  return (
    <div className="fixed inset-0 z-[20]">
      {/* 遮罩层 */}
      <div
        className="absolute inset-0 overlay-backdrop"
        style={{
          background: 'rgba(0, 0, 0, 0.1)',
          opacity: shouldAnimate ? 1 : 0,
        }}
        onClick={onClose}
      />

      {/* 抽屉面板 */}
      <div
        className="absolute top-0 left-0 h-full z-drawer overflow-hidden"
        style={{
          width: `${width}px`,
          background: 'rgba(255, 255, 255, 0.55)',
          backdropFilter: 'blur(50px) saturate(180%)',
          WebkitBackdropFilter: 'blur(50px) saturate(180%)',
          borderRight: '1px solid rgba(255, 255, 255, 0.7)',
          boxShadow: 'inset 1px 0 0 rgba(255,255,255,0.8)',
          transform: shouldAnimate ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 280ms cubic-bezier(0.32, 0.72, 0, 1)',
        }}
        onTransitionEnd={handleTransitionEnd}
      >
        {children}
      </div>
    </div>
  );
};

export default Drawer;