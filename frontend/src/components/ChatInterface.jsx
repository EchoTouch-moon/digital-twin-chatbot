import React, { useState, useRef, useEffect } from 'react';
import MessageBubble from './MessageBubble';
import EmojiPicker from './EmojiPicker';
import { useChat } from '../hooks/useChat';

/**
 * 聊天界面 - 液态玻璃风格
 */
const ChatInterface = ({ selectedPersona, onToggleSidebar, isSidebarVisible }) => {
  const [input, setInput] = useState('');
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showWelcome, setShowWelcome] = useState(true);
  const [welcomeFading, setWelcomeFading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const { messages, isLoading, isLoadingHistory, sendMessage, clearChat, reloadHistory } = useChat(selectedPersona);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 当有消息时隐藏欢迎语
  useEffect(() => {
    if (messages.length > 0) {
      hideWelcome();
    }
  }, [messages.length]);

  // 自动隐藏欢迎语（8秒后）
  useEffect(() => {
    const timer = setTimeout(() => {
      if (showWelcome && messages.length === 0) {
        hideWelcome();
      }
    }, 8000);
    return () => clearTimeout(timer);
  }, [showWelcome, messages.length]);

  const hideWelcome = () => {
    setWelcomeFading(true);
    setTimeout(() => {
      setShowWelcome(false);
      setWelcomeFading(false);
    }, 250); // 匹配 iOS 退出动画时长
  };

  const handleSend = async (emojiData = null) => {
    if (isLoading) return;
    if (!input.trim() && !emojiData) return;

    const message = input.trim();
    setInput('');
    setShowEmojiPicker(false);
    await sendMessage(message, emojiData);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleEmojiSelect = (emoji) => {
    handleSend(emoji);
  };

  const handleEmojiButtonClick = () => {
    // 点击表情包按钮时隐藏欢迎语
    if (showWelcome) {
      hideWelcome();
    }
    setShowEmojiPicker(!showEmojiPicker);
  };

  // 清空对话（带确认）
  const handleClearChat = () => {
    if (messages.length === 0) return;

    if (window.confirm('确定要清空当前对话吗？\n\n注意：历史消息仍保留在服务器，刷新页面可恢复。')) {
      clearChat();
    }
  };

  // 加载历史消息时显示 loading
  if (isLoadingHistory) {
    return (
      <div className="flex flex-col h-screen items-center justify-center">
        <div className="loading-spinner"></div>
        <p className="text-gray-500 mt-4">正在加载对话历史...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      {/* 顶栏 - 液态玻璃 */}
      <header className="glass glass-border h-14 flex items-center justify-between px-5 rounded-2xl mx-6 mt-6">
        <div className="flex items-center gap-4">
          {/* 汉堡菜单 */}
          <button
            onClick={onToggleSidebar}
            className="p-2 hover:bg-black/5 rounded-xl transition-colors"
          >
            <svg className="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* 角色名 */}
          <h1 className="text-lg font-semibold text-gray-800">
            {selectedPersona ? selectedPersona.name : '智能助手'}
          </h1>
        </div>

        {/* 清空按钮和恢复按钮 */}
        <div className="flex items-center gap-2">
          {/* 恢复按钮：当消息为空但有历史时显示 */}
          {messages.length === 0 && selectedPersona && (
            <button
              onClick={reloadHistory}
              className="p-2 hover:bg-black/5 rounded-xl transition-colors"
              title="恢复历史对话"
            >
              <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          )}

          <button
            onClick={handleClearChat}
            className="p-2 hover:bg-black/5 rounded-xl transition-colors"
            title="清空对话"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </header>

      {/* 消息区域 */}
      <main className="flex-1 overflow-y-auto chat-scrollbar py-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center px-8">
            {/* 欢迎语 - 带动效 */}
            {showWelcome && (
              <div
                className={`glass glass-border rounded-3xl p-10 text-center ${
                  welcomeFading
                    ? 'opacity-0 scale-95 translate-y-4'
                    : 'opacity-100 scale-100 translate-y-0 animate-float'
                }`}
                style={{
                  animationDelay: '0.3s',
                  transition: 'all 0.25s cubic-bezier(0.36, 0, 0.66, -0.56)',
                }}
              >
                <div className="text-6xl mb-5 animate-wave">👋</div>
                <p className="text-xl font-medium text-gray-800 mb-2">你好！</p>
                <p className="text-sm text-gray-500">我是你的AI聊天助手</p>
              </div>
            )}
          </div>
        ) : (
          <div className="px-6 flex flex-col">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </main>

      {/* 输入区域 - 液态玻璃 */}
      <footer className="glass glass-border rounded-3xl m-6 p-4">
        <div className="flex items-center gap-3 max-w-[640px] mx-auto">
          {/* 表情按钮 */}
          <div className="relative">
            <button
              onClick={handleEmojiButtonClick}
              disabled={isLoading}
              className="w-11 h-11 flex items-center justify-center hover:bg-black/5 rounded-full transition-colors disabled:opacity-50"
            >
              <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </button>
            <EmojiPicker
              isOpen={showEmojiPicker}
              onClose={() => setShowEmojiPicker(false)}
              onSelect={handleEmojiSelect}
              inputText={input}
            />
          </div>

          {/* 输入框 */}
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            disabled={isLoading}
            className="flex-1 h-12 px-5 bg-white/50 rounded-2xl text-[15px] text-gray-800 placeholder-gray-400 focus:outline-none focus:bg-white/70 disabled:opacity-50 transition-colors"
          />

          {/* 发送按钮 */}
          <button
            onClick={() => handleSend()}
            disabled={(!input.trim() && !showEmojiPicker) || isLoading}
            className="h-12 px-6 bg-gray-800/90 hover:bg-gray-800 text-white text-[15px] font-medium rounded-2xl disabled:bg-gray-300 disabled:text-gray-500 transition-all flex items-center justify-center"
          >
            {isLoading ? (
              <div className="loading-spinner text-white"></div>
            ) : (
              '发送'
            )}
          </button>
        </div>
      </footer>
    </div>
  );
};

export default ChatInterface;