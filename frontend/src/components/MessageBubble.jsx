import React from 'react';

/**
 * 卡片式消息气泡 - 液态玻璃风格
 * 用户消息靠右，助手消息靠左
 */
const MessageBubble = ({ message }) => {
  const isUser = message.role === 'user';
  const hasImage = message.imageUrl;
  const isEmoji = message.isEmoji;

  return (
    <div
      className={`flex mb-4 animate-message-appear ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      {isUser ? (
        <div className="flex items-end gap-3 flex-row-reverse max-w-[75%]">
          {/* 用户头像 */}
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, #FF6B6B, #FFA07A)',
              boxShadow: '0 4px 15px rgba(255,107,107,0.3)'
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
        <div className="flex items-start gap-3 max-w-[75%]">
          {/* 助手头像 */}
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, #32ADE6, #5856D6)',
              boxShadow: '0 4px 15px rgba(50,173,230,0.3)'
            }}
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
 * 消息内容卡片 - 液态玻璃
 */
const MessageContent = ({ message, isUser, hasImage, isEmoji }) => {
  // 表情包消息：优先显示表情包
  if (isEmoji && hasImage) {
    return (
      <div
        className="glass glass-border rounded-2xl"
        style={{ padding: '10px 12px' }}
      >
        <img
          src={message.imageUrl}
          alt="表情包"
          className="rounded-xl cursor-pointer hover:opacity-90 transition-opacity"
          style={{ maxWidth: '120px', maxHeight: '120px' }}
          loading="lazy"
          onClick={() => window.open(message.imageUrl, '_blank')}
          onError={(e) => {
            e.target.style.display = 'none';
          }}
        />
        {message.content && (
          <p className="text-sm text-gray-700 mt-2">{message.content}</p>
        )}
      </div>
    );
  }

  // 普通消息：文字 + 可选图片
  return (
    <div
      className="glass glass-border rounded-2xl"
      style={{ padding: '14px 18px' }}
    >
      {/* 文字内容 */}
      {message.content && (
        <p
          className="text-[15px] text-gray-800 leading-relaxed"
          style={{ lineHeight: 1.6 }}
        >
          {message.content}
        </p>
      )}

      {/* 图片 */}
      {hasImage && (
        <img
          src={message.imageUrl}
          alt="图片"
          className="rounded-xl cursor-pointer hover:opacity-90 transition-opacity mt-3"
          style={{ maxWidth: '200px' }}
          loading="lazy"
          onClick={() => window.open(message.imageUrl, '_blank')}
        />
      )}

      {/* 表情包信息提示 */}
      {message.emojiInfo && !message.isError && (
        <div className="mt-2 text-xs text-gray-400">
          {message.emojiInfo.sub_category} · 匹配度 {Math.round((message.emojiInfo.score || 0) * 100)}%
        </div>
      )}
    </div>
  );
};

export default MessageBubble;