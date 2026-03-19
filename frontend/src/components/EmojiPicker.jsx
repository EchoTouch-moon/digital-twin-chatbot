import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

/**
 * 表情包选择器 - 液态玻璃风格，丝滑动画
 */
const EmojiPicker = ({ isOpen, onClose, onSelect, inputText }) => {
  const [emojis, setEmojis] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isClosing, setIsClosing] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setIsVisible(true);
      setIsClosing(false);
      recommendEmojis(inputText || '');
    }
  }, [isOpen, inputText]);

  // 处理关闭动画
  const handleClose = () => {
    setIsClosing(true);
  };

  const handleAnimationEnd = () => {
    if (isClosing) {
      setIsVisible(false);
      setIsClosing(false);
      onClose();
    }
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target) && !isClosing) {
        handleClose();
      }
    };

    if (isVisible && !isClosing) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isVisible, isClosing]);

  const recommendEmojis = async (text) => {
    if (!text) {
      loadRandomEmojis();
      return;
    }
    setIsLoading(true);
    try {
      const response = await axios.post('/api/emoji/recommend', {
        text: text,
        top_k: 12
      });
      setEmojis(response.data.results || []);
    } catch (error) {
      console.error('Failed to recommend emojis:', error);
      setEmojis([]);
    } finally {
      setIsLoading(false);
    }
  };

  const loadRandomEmojis = async () => {
    setIsLoading(true);
    try {
      const promises = Array(12).fill(null).map(() =>
        axios.get('/api/emojis/random')
      );
      const responses = await Promise.all(promises);
      setEmojis(responses.map(r => r.data));
    } catch (error) {
      console.error('Failed to load random emojis:', error);
      setEmojis([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      await recommendEmojis(searchQuery);
    }
  };

  const handleEmojiClick = (emoji) => {
    onSelect(emoji);
    handleClose();
  };

  if (!isVisible) return null;

  return (
    <div
      ref={containerRef}
      className={`absolute bottom-full left-0 mb-3 rounded-2xl overflow-hidden z-picker ${
        isClosing ? 'animate-picker-out' : 'animate-fade-in'
      }`}
      style={{
        width: '320px',
        maxHeight: '380px',
        background: 'rgba(255, 255, 255, 0.55)',
        backdropFilter: 'blur(50px) saturate(180%)',
        WebkitBackdropFilter: 'blur(50px) saturate(180%)',
        border: '1px solid rgba(255, 255, 255, 0.8)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.1), inset 0 1px 1px rgba(255,255,255,0.8)',
        transformOrigin: 'bottom center',
      }}
      onAnimationEnd={handleAnimationEnd}
    >
      {/* 头部 */}
      <div className="p-4 border-b border-gray-200/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-gray-700">选择表情包</span>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors duration-150"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {/* 搜索框 */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="输入关键词..."
            className="flex-1 px-4 py-2.5 text-sm bg-white/60 rounded-xl text-gray-800 placeholder-gray-400 focus:outline-none focus:bg-white/80 transition-colors duration-150"
          />
          <button
            type="submit"
            className="px-4 py-2.5 bg-gray-800/90 hover:bg-gray-800 text-white text-sm rounded-xl font-medium transition-colors duration-150"
          >
            搜索
          </button>
        </form>
      </div>

      {/* 表情包网格 */}
      <div className="p-3 overflow-y-auto chat-scrollbar" style={{ maxHeight: '250px' }}>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <div className="loading-spinner text-gray-400"></div>
          </div>
        ) : emojis.length === 0 ? (
          <div className="text-center text-gray-400 py-10 text-sm">
            没有找到表情包
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-2">
            {emojis.map((emoji, index) => (
              <button
                key={index}
                onClick={() => handleEmojiClick(emoji)}
                className="rounded-xl overflow-hidden bg-white/50 hover:bg-white/80 transition-all duration-150 flex items-center justify-center border border-gray-100/50"
                style={{ width: '64px', height: '64px' }}
                title={emoji.description || emoji.sub_category}
              >
                <img
                  src={emoji.image_url}
                  alt={emoji.description || 'emoji'}
                  style={{ width: '54px', height: '54px', objectFit: 'contain' }}
                  loading="lazy"
                />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 推荐提示 */}
      {inputText && (
        <div className="px-4 py-2.5 bg-gray-50/50 text-xs text-gray-500 border-t border-gray-100/50">
          根据「{inputText.slice(0, 15)}...」推荐
        </div>
      )}
    </div>
  );
};

export default EmojiPicker;