import { useState, useRef, useCallback, useEffect } from 'react';
import axios from 'axios';

const API_BASE_URL = '';

/**
 * 聊天 Hook - 支持消息持久化
 *
 * 功能：
 * 1. 普通聊天（使用 /api/chat/fast）
 * 2. 个性化聊天（使用 /api/chat/personalized，需要角色ID）
 * 3. 支持记忆功能
 * 4. 支持发送表情包
 * 5. 支持历史消息加载（自动加载上次对话）
 */
export const useChat = (selectedPersona = null) => {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);

  const abortControllerRef = useRef(null);
  // Use ref to access latest messages without creating dependency cycle
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // 加载历史消息
  const loadHistory = useCallback(async (personaId) => {
    if (!personaId) return;

    setIsLoadingHistory(true);
    setError(null);

    try {
      const response = await axios.get(`${API_BASE_URL}/api/personas/${personaId}/session`);
      const { session_id, messages: historyMessages } = response.data;

      setSessionId(session_id);
      setMessages(historyMessages);

      console.log(`[useChat] Loaded ${historyMessages.length} messages for persona ${personaId}`);
    } catch (err) {
      console.error('[useChat] Failed to load history:', err);
      // 加载失败时清空消息，让用户重新开始
      setMessages([]);
      setSessionId(null);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  // Persona 变化时自动加载历史消息
  useEffect(() => {
    if (selectedPersona?.id) {
      loadHistory(selectedPersona.id);
    } else {
      // 没有 Persona 时清空消息
      setMessages([]);
      setSessionId(null);
    }
  }, [selectedPersona?.id, loadHistory]);

  const sendMessage = useCallback(async (content, emojiData = null) => {
    // 至少要有文字或表情包
    if (!content.trim() && !emojiData) return;

    // 构建用户消息
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: content || '',
      timestamp: new Date().toISOString(),
    };

    // 如果发送了表情包，添加到消息中
    if (emojiData) {
      userMessage.imageUrl = emojiData.image_url;
      userMessage.emojiInfo = emojiData;
      userMessage.isEmoji = true;
    }

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      // Use messagesRef to get latest messages without dependency cycle
      const history = messagesRef.current.slice(-10).map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));

      let response;

      // 如果选择了角色，使用个性化聊天接口
      if (selectedPersona?.id) {
        const requestData = {
          message: content || '',
          persona_id: selectedPersona.id,
          session_id: sessionId, // 发送 session_id
          history,
          use_memory: true, // 启用记忆功能
        };

        // 如果发送了表情包，添加表情包信息
        if (emojiData) {
          // 直接传递完整的 image_url 和文件名
          requestData.user_emoji_url = emojiData.image_url || '';
          requestData.user_emoji_description = emojiData.description || emojiData.sub_category || '表情包';
        }

        response = await axios.post(
          `${API_BASE_URL}/api/chat/personalized`,
          requestData,
          {
            signal: abortControllerRef.current.signal,
            timeout: 60000, // 个性化聊天可能需要更长时间
          }
        );

        // 更新 sessionId（后端可能返回新创建的）
        if (response.data.session_id) {
          setSessionId(response.data.session_id);
        }
      } else {
        // 否则使用普通快速聊天接口
        response = await axios.post(
          `${API_BASE_URL}/api/chat/fast`,
          {
            message: content,
            history,
          },
          {
            signal: abortControllerRef.current.signal,
            timeout: 30000,
          }
        );
      }

      const { text, image_url, emoji_info, memory_used } = response.data;

      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: text,
        imageUrl: image_url,
        emojiInfo: emoji_info,
        memoryUsed: memory_used, // 是否使用了记忆
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      console.error('Chat error:', err);

      let errorMessage = '发送失败，请稍后重试';

      if (axios.isCancel(err)) {
        errorMessage = '请求已取消';
      } else if (err.code === 'ECONNREFUSED') {
        errorMessage = '无法连接到服务器，请检查后端是否已启动';
      } else if (err.response?.status === 429) {
        errorMessage = '请求过于频繁，请稍后重试';
      } else if (err.response?.status === 404) {
        errorMessage = '角色不存在，请重新选择角色';
      } else if (err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      }

      setError(errorMessage);

      const errorAssistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `❌ ${errorMessage}`,
        isError: true,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, errorAssistantMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [selectedPersona, sessionId]);

  // 清空对话只清前端，后端保留
  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    // 注意：不清空 sessionId，保留与后端的关联
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // 重新加载历史（用于恢复清空的对话）
  const reloadHistory = useCallback(() => {
    if (selectedPersona?.id) {
      loadHistory(selectedPersona.id);
    }
  }, [selectedPersona?.id, loadHistory]);

  return {
    messages,
    isLoading,
    isLoadingHistory,
    error,
    sessionId,
    sendMessage,
    clearChat,
    loadHistory,
    reloadHistory,
  };
};