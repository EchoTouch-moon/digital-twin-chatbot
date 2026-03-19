# 前端 Apple 极简风格改造 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将微信风格聊天界面改造为 Apple 官网极简风格

**Architecture:**
1. 先更新设计系统（Tailwind配置 + 全局CSS）
2. 创建可复用的抽屉组件
3. 逐个改造现有组件（从底层到顶层）

**Tech Stack:** React 18, Tailwind CSS, Vite

---

## 文件结构

```
frontend/src/
├── App.jsx                    # [修改] 抽屉状态管理
├── index.css                  # [修改] 全局样式、CSS变量
├── components/
│   ├── ChatInterface.jsx      # [修改] 顶栏、消息区、输入区
│   ├── MessageBubble.jsx      # [修改] 卡片式消息
│   ├── PersonaManager.jsx     # [修改] 抽屉内容
│   ├── EmojiPicker.jsx        # [修改] 极简样式
│   └── Drawer.jsx             # [新建] 可复用抽屉组件
tailwind.config.js             # [修改] 颜色配置
```

---

## Chunk 1: 设计系统基础

### Task 1: 更新 Tailwind 颜色配置

**Files:**
- Modify: `frontend/tailwind.config.js`

- [ ] **Step 1: 更新 Tailwind 配置**

```javascript
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
        'drawer-slide': 'drawerSlide 300ms ease-out',
        'fade-in': 'fadeIn 200ms ease',
        'message-appear': 'messageAppear 200ms ease-out',
      },
      keyframes: {
        drawerSlide: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        messageAppear: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
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
```

- [ ] **Step 2: 验证配置**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

### Task 2: 更新全局 CSS 样式

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: 重写全局样式**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: #FFFFFF;
  color: #1D1D1F;
}

/* Apple-style scrollbar */
.chat-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.chat-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.chat-scrollbar::-webkit-scrollbar-thumb {
  background-color: #D1D1D6;
  border-radius: 3px;
}

.chat-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: #A1A1A6;
}

/* Message card scrollbar */
.message-card-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.message-card-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.message-card-scrollbar::-webkit-scrollbar-thumb {
  background-color: #D1D1D6;
  border-radius: 2px;
}

/* Drawer overlay */
.drawer-overlay {
  background-color: rgba(0, 0, 0, 0.3);
  animation: fadeIn 200ms ease;
}

/* Loading spinner */
.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
```

- [ ] **Step 2: 验证样式**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

## Chunk 2: 抽屉组件

### Task 3: 创建可复用抽屉组件

**Files:**
- Create: `frontend/src/components/Drawer.jsx`

- [ ] **Step 1: 创建 Drawer 组件**

```jsx
import React, { useEffect } from 'react';

/**
 * 可复用抽屉组件
 *
 * @param {boolean} isOpen - 是否打开
 * @param {function} onClose - 关闭回调
 * @param {ReactNode} children - 抽屉内容
 * @param {number} width - 抽屉宽度，默认280px
 */
const Drawer = ({ isOpen, onClose, children, width = 280 }) => {
  // ESC键关闭
  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  // 打开时禁止背景滚动
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[20]">
      {/* 遮罩层 */}
      <div
        className="absolute inset-0 drawer-overlay"
        onClick={onClose}
      />

      {/* 抽屉面板 */}
      <div
        className="absolute top-0 left-0 h-full bg-white/95 animate-drawer-slide z-drawer"
        style={{ width: `${width}px`, boxShadow: '0 0 20px rgba(0,0,0,0.1)' }}
      >
        {children}
      </div>
    </div>
  );
};

export default Drawer;
```

- [ ] **Step 2: 验证组件**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

### Task 4: 重构 PersonaManager 为抽屉内容

**Files:**
- Modify: `frontend/src/components/PersonaManager.jsx`

- [ ] **Step 1: 重写 PersonaManager 组件**

```jsx
import React, { useState } from 'react';

/**
 * 角色管理抽屉内容
 */
const PersonaManager = ({
  personas,
  selectedPersona,
  memories,
  userProfile,
  memorySummaries,
  isLoading,
  error,
  onSelectPersona,
  onCreatePersona,
  onGenerateProfile,
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [newPersonaName, setNewPersonaName] = useState('');
  const [newPersonaDescription, setNewPersonaDescription] = useState('');
  const [activeTab, setActiveTab] = useState('personas');

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newPersonaName.trim()) return;
    try {
      await onCreatePersona(newPersonaName.trim(), newPersonaDescription.trim());
      setNewPersonaName('');
      setNewPersonaDescription('');
      setIsCreating(false);
    } catch (err) {
      // 错误已在 hook 中处理
    }
  };

  const handleGenerateProfile = async () => {
    if (selectedPersona?.id) {
      await onGenerateProfile(selectedPersona.id);
    }
  };

  const getStageName = (stage) => {
    const stageNames = {
      'acquaintance': '初识阶段',
      'friend': '朋友阶段',
      'close_friend': '好友阶段',
      'best_friend': '挚友阶段'
    };
    return stageNames[stage] || stage;
  };

  return (
    <div className="h-full flex flex-col">
      {/* 当前角色头部 */}
      {selectedPersona && (
        <div className="p-5 border-b border-apple-border">
          <div className="flex items-center gap-4">
            <div
              className="w-15 h-15 rounded-full flex items-center justify-center text-white text-2xl font-medium"
              style={{
                width: '60px',
                height: '60px',
                background: 'linear-gradient(135deg, #FF6B6B, #FFA07A)'
              }}
            >
              {selectedPersona.name.charAt(0)}
            </div>
            <div>
              <h2 className="text-lg font-medium text-apple-text">{selectedPersona.name}</h2>
              {selectedPersona.description && (
                <p className="text-sm text-apple-text-secondary mt-0.5">{selectedPersona.description}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 分段控件 */}
      <div className="p-3">
        <div className="bg-apple-bg-secondary rounded-lg p-0.5 flex">
          {['personas', 'memories', 'profile'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2 text-sm rounded-md transition-all duration-150 ${
                activeTab === tab
                  ? 'bg-white text-apple-text font-medium shadow-apple-card'
                  : 'text-apple-text-secondary'
              }`}
            >
              {tab === 'personas' && '角色'}
              {tab === 'memories' && '记忆'}
              {tab === 'profile' && '画像'}
            </button>
          ))}
        </div>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto chat-scrollbar">
        {/* 角色列表 */}
        {activeTab === 'personas' && (
          <div className="p-3 space-y-1">
            {/* 创建角色按钮 */}
            {!isCreating ? (
              <button
                onClick={() => setIsCreating(true)}
                className="w-full py-3 text-sm text-apple-text-secondary border border-apple-border rounded-apple hover:bg-apple-bg-secondary transition-colors"
              >
                + 创建新角色
              </button>
            ) : (
              <form onSubmit={handleCreate} className="p-3 bg-apple-bg-secondary rounded-apple space-y-3">
                <input
                  type="text"
                  placeholder="角色名称"
                  value={newPersonaName}
                  onChange={(e) => setNewPersonaName(e.target.value)}
                  className="w-full px-3 py-2 bg-white border border-apple-border rounded-lg text-sm focus:outline-none focus:border-apple-blue"
                  autoFocus
                />
                <textarea
                  placeholder="角色描述（可选）"
                  value={newPersonaDescription}
                  onChange={(e) => setNewPersonaDescription(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 bg-white border border-apple-border rounded-lg text-sm focus:outline-none focus:border-apple-blue resize-none"
                />
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={!newPersonaName.trim() || isLoading}
                    className="flex-1 py-2 bg-apple-blue text-white text-sm rounded-pill font-medium disabled:bg-apple-disabled"
                  >
                    创建
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreating(false);
                      setNewPersonaName('');
                      setNewPersonaDescription('');
                    }}
                    className="flex-1 py-2 bg-apple-bg-secondary text-apple-text text-sm rounded-pill font-medium"
                  >
                    取消
                  </button>
                </div>
              </form>
            )}

            {/* 错误提示 */}
            {error && (
              <div className="p-3 bg-red-50 text-red-600 text-sm rounded-apple">
                {error}
              </div>
            )}

            {/* 角色列表 */}
            {personas.map((persona) => (
              <button
                key={persona.id}
                onClick={() => onSelectPersona(persona)}
                className={`w-full p-3 rounded-lg flex items-center gap-3 transition-colors ${
                  selectedPersona?.id === persona.id
                    ? 'bg-apple-bg-secondary border-l-[3px] border-apple-blue'
                    : 'hover:bg-apple-bg-secondary'
                }`}
                style={{ height: '56px' }}
              >
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-white text-base"
                  style={{ background: 'linear-gradient(135deg, #FF6B6B, #FFA07A)' }}
                >
                  {persona.name.charAt(0)}
                </div>
                <div className="flex-1 text-left">
                  <div className="text-sm font-medium text-apple-text">{persona.name}</div>
                  {persona.description && (
                    <div className="text-xs text-apple-text-secondary truncate">{persona.description}</div>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}

        {/* 记忆列表 */}
        {activeTab === 'memories' && (
          <div className="p-3 space-y-2">
            {memories.length === 0 ? (
              <div className="text-center py-8 text-apple-text-secondary text-sm">
                还没有记忆，与角色对话会自动提取
              </div>
            ) : (
              memories.map((memory) => (
                <div
                  key={memory.id}
                  className="p-3 bg-apple-bg-secondary rounded-apple"
                >
                  <div className="flex items-start gap-2">
                    <span className="text-base">
                      {memory.memory_type === 'preference' && '❤️'}
                      {memory.memory_type === 'fact' && '💡'}
                      {memory.memory_type === 'event' && '📅'}
                      {memory.memory_type === 'topic' && '💬'}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm text-apple-text">{memory.content}</p>
                      <div className="flex items-center gap-2 mt-2 text-xs text-apple-text-secondary">
                        <span className="px-2 py-0.5 bg-white rounded">{memory.memory_type}</span>
                        <span>重要性: {memory.importance_score?.toFixed(1)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* 用户画像 */}
        {activeTab === 'profile' && (
          <div className="p-3 space-y-3">
            {!selectedPersona ? (
              <div className="text-center py-8 text-apple-text-secondary text-sm">
                请先选择一个角色
              </div>
            ) : !userProfile || userProfile.conversation_count === 0 ? (
              <div className="text-center py-8">
                <div className="text-apple-text-secondary text-sm mb-4">还没有用户画像</div>
                <button
                  onClick={handleGenerateProfile}
                  disabled={isLoading}
                  className="px-6 py-2 bg-apple-blue text-white text-sm rounded-pill font-medium disabled:bg-apple-disabled"
                >
                  {isLoading ? '生成中...' : '生成画像'}
                </button>
              </div>
            ) : (
              <>
                {/* 关系阶段 */}
                <div className="p-4 bg-gradient-to-br from-blue-50 to-purple-50 rounded-apple border border-apple-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-apple-text-secondary">关系阶段</span>
                    <span className="text-xs px-2 py-1 bg-apple-blue/10 text-apple-blue rounded-full">
                      信任度 {Math.round(userProfile.trust_level * 100)}%
                    </span>
                  </div>
                  <div className="text-base font-medium text-apple-blue">
                    {getStageName(userProfile.relationship_stage)}
                  </div>
                  <div className="text-xs text-apple-text-secondary mt-1">
                    基于 {userProfile.conversation_count} 条记忆
                  </div>
                </div>

                {/* 兴趣爱好 */}
                {userProfile.interests?.length > 0 && (
                  <div className="p-3 bg-apple-bg-secondary rounded-apple">
                    <h4 className="text-sm font-medium text-apple-text mb-2">兴趣爱好</h4>
                    <div className="flex flex-wrap gap-2">
                      {userProfile.interests.map((interest, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-1 bg-white border border-apple-border rounded text-xs text-apple-text-secondary"
                        >
                          {interest}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* 沟通风格 */}
                {userProfile.communication_style && (
                  <div className="p-3 bg-apple-bg-secondary rounded-apple">
                    <h4 className="text-sm font-medium text-apple-text mb-1">沟通特点</h4>
                    <p className="text-sm text-apple-text-secondary">{userProfile.communication_style}</p>
                  </div>
                )}

                {/* 背景信息 */}
                {userProfile.background_summary && (
                  <div className="p-3 bg-apple-bg-secondary rounded-apple">
                    <h4 className="text-sm font-medium text-apple-text mb-1">背景信息</h4>
                    <p className="text-sm text-apple-text-secondary whitespace-pre-line">
                      {userProfile.background_summary}
                    </p>
                  </div>
                )}

                {/* 记忆摘要 */}
                {memorySummaries?.length > 0 && (
                  <div className="p-3 bg-apple-bg-secondary rounded-apple">
                    <h4 className="text-sm font-medium text-apple-text mb-2">记忆摘要</h4>
                    <div className="space-y-2">
                      {memorySummaries.map((summary) => (
                        <div key={summary.id} className="p-2 bg-white rounded border border-apple-border">
                          <div className="text-xs font-medium text-apple-text">{summary.title}</div>
                          <div className="text-xs text-apple-text-secondary mt-1 line-clamp-2">
                            {summary.content}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 重新生成按钮 */}
                <button
                  onClick={handleGenerateProfile}
                  disabled={isLoading}
                  className="w-full py-2 bg-apple-bg-secondary text-apple-text-secondary text-sm rounded-apple hover:bg-apple-border transition-colors"
                >
                  {isLoading ? '更新中...' : '重新生成画像'}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default PersonaManager;
```

- [ ] **Step 2: 验证组件**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

## Chunk 3: 消息组件

### Task 5: 重构 MessageBubble 为卡片式

**Files:**
- Modify: `frontend/src/components/MessageBubble.jsx`

- [ ] **Step 1: 重写 MessageBubble 组件**

```jsx
import React from 'react';

/**
 * 卡片式消息气泡
 */
const MessageBubble = ({ message }) => {
  const isUser = message.role === 'user';
  const hasImage = message.imageUrl;
  const isEmoji = message.isEmoji;

  return (
    <div
      className={`flex mb-4 animate-message-appear ${isUser ? 'justify-end' : 'justify-start'}`}
      style={{ maxWidth: '480px' }}
    >
      {isUser ? (
        // 用户消息：右对齐，头像在右下
        <div className="flex items-end gap-2 flex-row-reverse">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, #FF6B6B, #FFA07A)'
            }}
          >
            😊
          </div>
          <MessageContent
            message={message}
            isUser={isUser}
            hasImage={hasImage}
            isEmoji={isEmoji}
          />
        </div>
      ) : (
        // AI消息：左对齐，头像在左上
        <div className="flex items-start gap-2">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm flex-shrink-0"
            style={{ background: '#007AFF' }}
          >
            🤖
          </div>
          <MessageContent
            message={message}
            isUser={isUser}
            hasImage={hasImage}
            isEmoji={isEmoji}
          />
        </div>
      )}
    </div>
  );
};

/**
 * 消息内容卡片
 */
const MessageContent = ({ message, isUser, hasImage, isEmoji }) => {
  return (
    <div
      className="bg-white border border-apple-border rounded-apple"
      style={{ padding: '12px 16px' }}
    >
      {/* 表情包消息 */}
      {isEmoji && hasImage ? (
        <>
          <img
            src={message.imageUrl}
            alt="表情包"
            className="rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
            style={{ maxWidth: '150px' }}
            loading="lazy"
            onClick={() => window.open(message.imageUrl, '_blank')}
          />
          {message.content && (
            <p className="text-sm text-apple-text mt-2">{message.content}</p>
          )}
        </>
      ) : (
        <>
          {/* 文字内容 */}
          {message.content && (
            <p
              className="text-[15px] text-apple-text leading-relaxed"
              style={{ lineHeight: 1.5 }}
            >
              {message.content}
            </p>
          )}

          {/* 图片 */}
          {hasImage && (
            <img
              src={message.imageUrl}
              alt="图片"
              className="rounded-lg cursor-pointer hover:opacity-90 transition-opacity mt-2"
              style={{ maxWidth: '200px' }}
              loading="lazy"
              onClick={() => window.open(message.imageUrl, '_blank')}
            />
          )}
        </>
      )}

      {/* 错误提示 */}
      {message.emojiInfo && message.isError && (
        <div className="mt-2 text-xs text-apple-text-secondary">
          {message.emojiInfo.sub_category} · 匹配度 {Math.round(message.emojiInfo.score * 100)}%
        </div>
      )}
    </div>
  );
};

export default MessageBubble;
```

- [ ] **Step 2: 验证组件**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

## Chunk 4: 表情选择器

### Task 6: 简化 EmojiPicker 样式

**Files:**
- Modify: `frontend/src/components/EmojiPicker.jsx`

- [ ] **Step 1: 重写 EmojiPicker 组件**

```jsx
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

/**
 * 表情包选择器 - Apple 极简风格
 */
const EmojiPicker = ({ isOpen, onClose, onSelect, inputText }) => {
  const [emojis, setEmojis] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const containerRef = useRef(null);

  useEffect(() => {
    if (isOpen && inputText) {
      recommendEmojis(inputText);
    } else if (isOpen) {
      loadRandomEmojis();
    }
  }, [isOpen, inputText]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  const recommendEmojis = async (text) => {
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
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      ref={containerRef}
      className="absolute bottom-full left-0 mb-2 bg-white rounded-apple shadow-apple-picker z-picker"
      style={{ width: '320px', maxHeight: '360px' }}
    >
      {/* 头部 */}
      <div className="p-3 border-b border-apple-border">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-apple-text">选择表情包</span>
          <button
            onClick={onClose}
            className="text-apple-text-secondary hover:text-apple-text transition-colors"
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
            placeholder="输入关键词搜索..."
            className="flex-1 px-3 py-2 text-sm bg-apple-bg-secondary rounded-lg focus:outline-none"
          />
          <button
            type="submit"
            className="px-4 py-2 bg-apple-blue text-white text-sm rounded-pill font-medium"
          >
            搜索
          </button>
        </form>
      </div>

      {/* 表情包网格 */}
      <div className="p-3 overflow-y-auto chat-scrollbar" style={{ maxHeight: '240px' }}>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <div className="loading-spinner text-apple-blue"></div>
          </div>
        ) : emojis.length === 0 ? (
          <div className="text-center text-apple-text-secondary py-8 text-sm">
            没有找到表情包
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-2">
            {emojis.map((emoji, index) => (
              <button
                key={index}
                onClick={() => handleEmojiClick(emoji)}
                className="rounded-lg overflow-hidden border border-apple-border hover:border-apple-blue transition-all bg-apple-bg-secondary flex items-center justify-center"
                style={{ width: '64px', height: '64px' }}
                title={emoji.description || emoji.sub_category}
              >
                <img
                  src={emoji.image_url}
                  alt={emoji.description || 'emoji'}
                  style={{ width: '56px', height: '56px', objectFit: 'contain' }}
                  loading="lazy"
                />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 推荐提示 */}
      {inputText && (
        <div className="px-3 py-2 bg-apple-bg-secondary text-xs text-apple-text-secondary border-t border-apple-border">
          根据「{inputText.slice(0, 20)}...」推荐
        </div>
      )}
    </div>
  );
};

export default EmojiPicker;
```

- [ ] **Step 2: 验证组件**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

## Chunk 5: 聊天界面

### Task 7: 重构 ChatInterface

**Files:**
- Modify: `frontend/src/components/ChatInterface.jsx`

- [ ] **Step 1: 重写 ChatInterface 组件**

```jsx
import React, { useState, useRef, useEffect } from 'react';
import MessageBubble from './MessageBubble';
import EmojiPicker from './EmojiPicker';
import { useChat } from '../hooks/useChat';

/**
 * 聊天界面 - Apple 极简风格
 */
const ChatInterface = ({ selectedPersona, onToggleSidebar, isSidebarVisible }) => {
  const [input, setInput] = useState('');
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const { messages, isLoading, sendMessage, clearChat } = useChat(selectedPersona);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* 顶栏 */}
      <header className="h-12 border-b border-apple-border flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          {/* 汉堡菜单 */}
          <button
            onClick={onToggleSidebar}
            className="p-1 hover:bg-apple-bg-secondary rounded transition-colors"
          >
            <svg className="w-5 h-5 text-apple-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* 角色名 */}
          <h1 className="text-[17px] font-medium text-apple-text">
            {selectedPersona ? selectedPersona.name : '智能助手'}
          </h1>
        </div>

        {/* 清空按钮 */}
        <button
          onClick={clearChat}
          className="p-2 hover:bg-apple-bg-secondary rounded transition-colors"
          title="清空对话"
        >
          <svg className="w-5 h-5 text-apple-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </header>

      {/* 消息区域 */}
      <main className="flex-1 overflow-y-auto chat-scrollbar">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-apple-text-secondary">
            <div className="text-4xl mb-4">👋</div>
            <p className="text-lg mb-1">你好！</p>
            <p className="text-sm">我是你的AI聊天助手</p>
          </div>
        ) : (
          <div className="py-4 px-4 flex flex-col items-center">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </main>

      {/* 输入区域 */}
      <footer className="border-t border-apple-border p-3">
        <div className="flex items-center gap-2 max-w-[600px] mx-auto">
          {/* 表情按钮 */}
          <div className="relative">
            <button
              onClick={() => setShowEmojiPicker(!showEmojiPicker)}
              disabled={isLoading}
              className="w-9 h-9 flex items-center justify-center hover:bg-apple-bg-secondary rounded-full transition-colors disabled:opacity-50"
            >
              <svg className="w-6 h-6 text-apple-text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
            className="flex-1 h-10 px-4 bg-apple-bg-secondary rounded-pill text-[15px] focus:outline-none disabled:opacity-50"
          />

          {/* 发送按钮 */}
          <button
            onClick={() => handleSend()}
            disabled={(!input.trim() && !showEmojiPicker) || isLoading}
            className="h-9 px-4 bg-apple-blue text-white text-[15px] font-medium rounded-pill disabled:bg-apple-disabled transition-colors flex items-center justify-center"
            style={{ minWidth: '60px' }}
          >
            {isLoading ? (
              <div className="loading-spinner"></div>
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
```

- [ ] **Step 2: 验证组件**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

## Chunk 6: 应用入口

### Task 8: 更新 App.jsx 集成抽屉

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: 重写 App 组件**

```jsx
import React, { useState } from 'react';
import ChatInterface from './components/ChatInterface';
import PersonaManager from './components/PersonaManager';
import Drawer from './components/Drawer';
import { usePersonas } from './hooks/usePersonas';

/**
 * 应用主组件 - Apple 极简风格
 */
function App() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const {
    personas,
    selectedPersona,
    memories,
    userProfile,
    memorySummaries,
    isLoading,
    error,
    createPersona,
    selectPersona,
    generateUserProfile,
  } = usePersonas();

  const handleSelectPersona = (persona) => {
    selectPersona(persona);
    setIsDrawerOpen(false);
  };

  return (
    <div className="h-screen bg-white overflow-hidden">
      {/* 聊天界面 */}
      <ChatInterface
        selectedPersona={selectedPersona}
        onToggleSidebar={() => setIsDrawerOpen(!isDrawerOpen)}
        isSidebarVisible={isDrawerOpen}
      />

      {/* 抽屉式侧边栏 */}
      <Drawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        width={280}
      >
        <PersonaManager
          personas={personas}
          selectedPersona={selectedPersona}
          memories={memories}
          userProfile={userProfile}
          memorySummaries={memorySummaries}
          isLoading={isLoading}
          error={error}
          onSelectPersona={handleSelectPersona}
          onCreatePersona={createPersona}
          onGenerateProfile={generateUserProfile}
        />
      </Drawer>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: 验证应用**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run build`
预期: 无错误

---

## Chunk 7: 验收测试

### Task 9: 启动并验证应用

- [ ] **Step 1: 启动后端服务**

运行: `cd /Users/v/new\ idea/wxdata_process/backend && source ~/miniconda3/etc/profile.d/conda.sh && conda activate wxdata && python main.py`
预期: 后端启动成功，监听8000端口

- [ ] **Step 2: 启动前端服务**

运行: `cd /Users/v/new\ idea/wxdata_process/frontend && npm run dev`
预期: 前端启动成功，访问 http://localhost:5173

- [ ] **Step 3: 验收检查清单**

- [ ] 页面背景纯白，无多余装饰
- [ ] 顶栏简洁，仅显示菜单图标、角色名、清空按钮
- [ ] 消息以卡片形式显示，居中对齐
- [ ] 点击汉堡菜单，抽屉从左侧滑出
- [ ] 抽屉带遮罩层，点击遮罩可关闭
- [ ] 输入框为胶囊形
- [ ] 发送按钮为苹果蓝
- [ ] 所有颜色符合设计规范
- [ ] 动画流畅自然

---

## 文件变更摘要

| 文件 | 操作 | 描述 |
|------|------|------|
| `tailwind.config.js` | 修改 | 添加 Apple 设计系统颜色、动画、阴影 |
| `src/index.css` | 修改 | 更新全局样式和滚动条样式 |
| `src/components/Drawer.jsx` | 新建 | 可复用抽屉组件 |
| `src/components/PersonaManager.jsx` | 修改 | 抽屉内容，分段控件，极简样式 |
| `src/components/MessageBubble.jsx` | 修改 | 卡片式消息设计 |
| `src/components/EmojiPicker.jsx` | 修改 | 极简风格表情选择器 |
| `src/components/ChatInterface.jsx` | 修改 | 极简顶栏、消息区、输入区 |
| `src/App.jsx` | 修改 | 集成抽屉组件 |