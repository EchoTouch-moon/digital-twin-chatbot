"""
LLM Service for the Digital Twin Chatbot.

This module handles all interactions with the LLM (Large Language Model),
including:
1. Intent analysis - determining if the user's message warrants an emoji response
2. Search query generation - creating optimized queries for emoji retrieval
3. Personalized chat response generation - creating conversational replies that mimic a persona
4. Integration with persona service and memory system
5. Emoji behavior-aware recommendations
6. Dynamic Prompt adaptation - three adaptive mechanisms for personalized responses
"""

import os
import random
from typing import Dict, Any, Optional, List
from openai import OpenAI
from pydantic import BaseModel

# Import emoji behavior service
try:
    from emoji_behavior_service import get_emoji_behavior_service
    EMOJI_BEHAVIOR_AVAILABLE = True
except ImportError:
    EMOJI_BEHAVIOR_AVAILABLE = False
    print("[LLM] Warning: Emoji behavior service not available")

# Import dynamic prompt service
try:
    from dynamic_prompt_service import get_dynamic_prompt_service, IntentResult
    DYNAMIC_PROMPT_AVAILABLE = True
except ImportError:
    DYNAMIC_PROMPT_AVAILABLE = False
    print("[LLM] Warning: Dynamic prompt service not available")

# Import advanced memory service
try:
    from advanced_memory_service import get_advanced_memory_service
    ADVANCED_MEMORY_AVAILABLE = True
except ImportError:
    ADVANCED_MEMORY_AVAILABLE = False
    print("[LLM] Warning: Advanced memory service not available")

# Import prompt truncator
try:
    from prompt_truncator import get_prompt_truncator
    PROMPT_TRUNCATOR_AVAILABLE = True
except ImportError:
    PROMPT_TRUNCATOR_AVAILABLE = False
    print("[LLM] Warning: Prompt truncator not available")


class LLMConfig(BaseModel):
    """Configuration for LLM service."""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 500


class IntentAnalysis(BaseModel):
    """Result of intent analysis."""
    needs_emoji: bool
    search_query: str
    reasoning: str


class LLMService:
    """
    Service for interacting with Large Language Models.
    Supports personalized responses based on digital twin personas.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize the LLM service."""
        if config is None:
            config = self._load_config_from_env()

        self.config = config
        # 创建OpenAI客户端，配置合理的超时时间
        import httpx

        # 配置超时：
        # - connect: 连接超时 5秒
        # - read: 读取超时 15秒（防止LLM卡顿拖垮服务）
        # - write: 写入超时 10秒
        # - pool: 连接池超时 20秒
        timeout_config = httpx.Timeout(
            connect=5.0,
            read=15.0,
            write=10.0,
            pool=20.0
        )

        http_client = httpx.Client(
            timeout=timeout_config,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )

        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            http_client=http_client
        )

        # Services for personalization (initialized on demand)
        self._persona_service = None
        self._memory_service = None
        self._emoji_behavior_service = None
        self._dynamic_prompt_service = None  # 新增：动态Prompt服务
        self._advanced_memory_service = None  # 新增：高级记忆服务

    def _get_advanced_memory_service(self):
        """Lazy load advanced memory service."""
        if self._advanced_memory_service is None and ADVANCED_MEMORY_AVAILABLE:
            from advanced_memory_service import get_advanced_memory_service
            self._advanced_memory_service = get_advanced_memory_service()
        return self._advanced_memory_service

    def _get_dynamic_prompt_service(self):
        """Lazy load dynamic prompt service."""
        if self._dynamic_prompt_service is None and DYNAMIC_PROMPT_AVAILABLE:
            from dynamic_prompt_service import get_dynamic_prompt_service
            self._dynamic_prompt_service = get_dynamic_prompt_service()
        return self._dynamic_prompt_service

    def _get_emoji_behavior_service(self):
        """Lazy load emoji behavior service."""
        if self._emoji_behavior_service is None and EMOJI_BEHAVIOR_AVAILABLE:
            from emoji_behavior_service import get_emoji_behavior_service
            self._emoji_behavior_service = get_emoji_behavior_service()
        return self._emoji_behavior_service

    def _load_config_from_env(self) -> LLMConfig:
        """Load configuration directly from .env file to avoid system env var conflicts."""
        from dotenv import dotenv_values

        # 从backend目录的 .env 文件加载配置
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        env_config = dotenv_values(config_path)

        print(f"[LLM] Loading config from {config_path}")
        print(f"[LLM] API Key from file: {env_config.get('OPENAI_API_KEY', '')[:10]}...")
        print(f"[LLM] Base URL from file: {env_config.get('OPENAI_BASE_URL', '')}")
        print(f"[LLM] Model from file: {env_config.get('OPENAI_MODEL', '')}")

        return LLMConfig(
            api_key=env_config.get("OPENAI_API_KEY", ""),
            base_url=env_config.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=env_config.get("OPENAI_MODEL", "gpt-3.5-turbo"),
            temperature=float(env_config.get("LLM_TEMPERATURE", "0.7")),
            max_tokens=int(env_config.get("LLM_MAX_TOKENS", "500"))
        )
    
    def _get_persona_service(self):
        """Lazy load persona service."""
        if self._persona_service is None:
            from persona_service import get_persona_service
            self._persona_service = get_persona_service()
        return self._persona_service
    
    def _get_memory_service(self):
        """Lazy load memory service."""
        if self._memory_service is None:
            from memory_service import get_memory_service
            self._memory_service = get_memory_service()
        return self._memory_service

    def analyze_intent(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        persona_id: Optional[int] = None,
        user_sent_emoji: bool = False
    ) -> IntentAnalysis:
        """
        Analyze user intent to determine if an emoji response is appropriate.

        重要：此方法会先检查用户的表情包使用习惯
        - 如果用户不使用表情包，直接返回 needs_emoji=False
        - 根据用户习惯决定是否推荐表情包

        Args:
            user_message: The user's message
            conversation_history: Previous conversation context
            persona_id: Optional persona ID for personalized analysis
            user_sent_emoji: Whether the user sent an emoji (increases response emoji probability)
        """
        # ===== 核心改进：先检查用户的表情包使用习惯 =====
        # 但如果用户发送了表情包，则跳过这个检查（因为用户发表情包说明愿意用表情包互动）
        if persona_id and not user_sent_emoji:
            emoji_behavior = self._get_emoji_behavior_service()
            if emoji_behavior:
                should_recommend = emoji_behavior.should_recommend_emoji(persona_id)
                if not should_recommend:
                    # 用户不使用表情包，尊重其习惯，不推荐
                    print(f"[LLM] Persona {persona_id} doesn't prefer emojis, skipping recommendation")
                    return IntentAnalysis(
                        needs_emoji=False,
                        search_query="",
                        reasoning="User's emoji usage frequency indicates no preference for emojis"
                    )
        # ====================================================

        # Build system prompt
        system_content = """You are an intent analysis assistant. Analyze user messages and determine if a visual response (emoji) would enhance the conversation naturally.

Rules:
1. If the user's message expresses emotion, humor, sarcasm, or would be enhanced by a visual response, set needs_emoji to true.
2. If the user is clearly asking for a recommendation (not specifically for emojis), but a visual response would complement your text reply, set needs_emoji to true.
3. If the message is purely informational, transactional, or formal, set needs_emoji to false.
4. When needs_emoji is true, generate a search_query that describes an appropriate visual response that complements your text reply.

Respond in JSON format:
{
    "needs_emoji": boolean,
    "search_query": "detailed description for visual response search",
    "reasoning": "brief explanation of your decision"
}"""
        
        # Add persona-specific guidance if available
        if persona_id:
            try:
                persona = self._get_persona_service().get_persona(persona_id)
                if persona and persona.emoji_preferences:
                    prefs = ", ".join(persona.emoji_preferences[:3])
                    system_content += f"\n\nThe persona typically uses these types of emojis: {prefs}. Consider this when determining if an emoji is appropriate."
            except Exception as e:
                print(f"[LLM] Error loading persona for intent analysis: {e}")
        
        messages = [{"role": "system", "content": system_content}]

        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-3:]:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", "")
                    })

        # 请求模型返回 JSON 格式的结果
        messages.append({
            "role": "user",
            "content": f'Analyze this message and respond ONLY with a valid JSON object (no other text). Format: {{"needs_emoji": true/false, "search_query": "keywords", "reasoning": "explanation"}}. Message: "{user_message}"'
        })

        try:
            print(f"[LLM] Sending intent analysis request...")

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=0.3,
                max_tokens=150
            )

            content = response.choices[0].message.content
            import json
            import re

            # 尝试从响应中提取 JSON（新模型不支持 response_format=json_object）
            # 首先尝试直接解析
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # 尝试从文本中提取 JSON 对象
                json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError("No valid JSON found in response")

            # 避免 Windows 控制台编码问题
            try:
                print(f"[LLM] Intent analysis result: {result}")
            except UnicodeEncodeError:
                print(f"[LLM] Intent analysis result: [contains emoji]")
            return IntentAnalysis(
                needs_emoji=result.get("needs_emoji", False),
                search_query=result.get("search_query", ""),
                reasoning=result.get("reasoning", "")
            )

        except Exception as e:
            print(f"[LLM] Error in intent analysis: {type(e).__name__}: {e}")
            import traceback
            print(f"[LLM] Traceback: {traceback.format_exc()}")
            # 出错时根据消息内容智能判断
            return self._fallback_intent_analysis(user_message)

    def generate_personalized_response(
        self,
        user_message: str,
        persona_id: int,
        session_id: Optional[int] = None,
        retrieved_emoji: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        use_memory: bool = True,
        use_similar_conversations: bool = True,
        stream: bool = False,
        user_sent_emoji: bool = False,
        use_dynamic_prompt: bool = True  # 新增：是否使用动态Prompt
    ):
        """
        Generate a personalized response based on a digital twin persona.

        支持三种动态适应机制：
        1. 语义化记忆检索 - 基于向量相似度检索相关记忆
        2. 意图感知模板选择 - 根据对话意图选择Prompt模板
        3. 持续学习更新 - 自动更新Persona特征

        Args:
            user_message: The user's message
            persona_id: ID of the persona to mimic
            session_id: Optional session ID for memory context
            retrieved_emoji: Optional emoji to include
            conversation_history: Previous conversation messages
            use_memory: Whether to include relevant memories
            use_similar_conversations: Whether to include similar past conversations
            stream: Whether to stream the response
            user_sent_emoji: Whether the user sent an emoji
            use_dynamic_prompt: Whether to use dynamic prompt mechanisms

        Returns:
            If stream=True: Generator yielding text chunks
            If stream=False: Complete response string
        """
        # 获取Persona
        persona = None
        try:
            persona_service = self._get_persona_service()
            persona = persona_service.get_persona(persona_id)
        except Exception as e:
            print(f"[LLM] Error getting persona: {e}")

        # ===== 动态Prompt机制 =====
        if use_dynamic_prompt and DYNAMIC_PROMPT_AVAILABLE and persona:
            try:
                dynamic_service = self._get_dynamic_prompt_service()
                if dynamic_service:
                    return self._generate_with_dynamic_prompt(
                        user_message=user_message,
                        persona=persona,
                        persona_id=persona_id,
                        dynamic_service=dynamic_service,
                        retrieved_emoji=retrieved_emoji,
                        conversation_history=conversation_history,
                        stream=stream,
                        user_sent_emoji=user_sent_emoji,
                        session_id=session_id  # 新增：传递session_id用于三层记忆
                    )
            except Exception as e:
                print(f"[LLM] Dynamic prompt failed, falling back: {e}")

        # ===== 传统Prompt方式（回退） =====
        return self._generate_with_traditional_prompt(
            user_message=user_message,
            persona_id=persona_id,
            session_id=session_id,
            retrieved_emoji=retrieved_emoji,
            conversation_history=conversation_history,
            use_memory=use_memory,
            use_similar_conversations=use_similar_conversations,
            stream=stream,
            user_sent_emoji=user_sent_emoji
        )

    def _generate_with_dynamic_prompt(
        self,
        user_message: str,
        persona: Any,
        persona_id: int,
        dynamic_service: Any,
        retrieved_emoji: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        stream: bool = False,
        user_sent_emoji: bool = False,
        session_id: Optional[int] = None
    ):
        """
        使用动态Prompt机制生成回复

        三种动态适应：
        1. 语义化记忆检索
        2. 意图感知模板选择
        3. 持续学习更新（后台触发）

        新增：三层记忆架构集成
        - L1 热记忆：直接注入System Prompt
        - L2 日记层：近期对话摘要
        - L3 向量层：语义检索
        """
        # 1. 意图识别
        intent = dynamic_service.classify_intent(user_message)
        print(f"[LLM Dynamic] Detected intent: {intent.intent_type}, emotion: {intent.emotion}")

        # 2. 获取三层记忆上下文
        memory_contexts = {}
        if ADVANCED_MEMORY_AVAILABLE:
            try:
                advanced_memory = self._get_advanced_memory_service()
                if advanced_memory:
                    memory_contexts = advanced_memory.get_all_memory_context(
                        persona_id=persona_id,
                        session_id=session_id,
                        user_message=user_message,
                        include_hot=True,
                        include_journals=True,
                        include_cold=True
                    )
                    print(f"[LLM Dynamic] Memory layers: hot={bool(memory_contexts.get('hot_memory'))}, journals={bool(memory_contexts.get('journals'))}, cold={bool(memory_contexts.get('cold_memory'))}")
            except Exception as e:
                print(f"[LLM Dynamic] Advanced memory error: {e}")

        # 3. 语义化记忆检索（保留原有逻辑作为L3补充）
        memories = dynamic_service.retrieve_memories(persona_id, user_message, top_k=3)
        legacy_memory_context = dynamic_service.get_memory_context_string(memories) if memories else ""

        # 4. 获取对话示例
        examples = []
        try:
            persona_service = self._get_persona_service()
            examples = persona_service._get_few_shot_examples(persona_id, 3)
        except:
            pass

        # 5. 构建动态Prompt
        system_prompt = dynamic_service.build_dynamic_prompt(
            intent=intent,
            persona=persona,
            memories=memories,
            examples=examples
        )

        # 5.5 准备记忆上下文并截断（防止Prompt膨胀）
        # 合并所有记忆上下文
        all_memory_contexts = {}

        if memory_contexts.get("hot_memory"):
            all_memory_contexts["hot_memory"] = memory_contexts["hot_memory"]

        if memory_contexts.get("scratchpad"):
            all_memory_contexts["scratchpad"] = memory_contexts["scratchpad"]

        if memory_contexts.get("journals"):
            all_memory_contexts["journals"] = memory_contexts["journals"]

        if legacy_memory_context:
            all_memory_contexts["legacy_memory"] = legacy_memory_context

        if memory_contexts.get("cold_memory"):
            all_memory_contexts["cold_memory"] = memory_contexts["cold_memory"]

        # 使用PromptTruncator进行截断（解决"迷失在中间"问题）
        truncation_stats = None
        if PROMPT_TRUNCATOR_AVAILABLE and all_memory_contexts:
            try:
                truncator = get_prompt_truncator(self.config.model)
                # 为System Prompt预留空间，截断记忆上下文
                truncated_contexts, truncation_stats = truncator.truncate_context(
                    all_memory_contexts,
                    max_tokens=1500,  # 记忆上下文最多1500 tokens
                    system_prompt_tokens=len(system_prompt) // 2  # 估算System Prompt的tokens
                )
                all_memory_contexts = truncated_contexts

                if truncation_stats and truncation_stats.get("total_original", 0) > truncation_stats.get("total_truncated", 0):
                    print(f"[LLM Dynamic] Truncated memory context: {truncation_stats['total_original']} -> {truncation_stats['total_truncated']} tokens")
            except Exception as e:
                print(f"[LLM Dynamic] Prompt truncation failed: {e}")

        # 6. 构建消息
        messages = [{"role": "system", "content": system_prompt}]

        # 按优先级添加记忆上下文
        for key in ["hot_memory", "scratchpad", "journals", "legacy_memory", "cold_memory"]:
            if all_memory_contexts.get(key):
                messages.append({"role": "system", "content": all_memory_contexts[key]})

        # 添加对话历史（最近5轮，约10条消息）
        if conversation_history:
            for msg in conversation_history[-10:]:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", "")
                    })

        # 7. 构建当前用户消息
        prompt = self._build_user_prompt(user_message, retrieved_emoji, user_sent_emoji, intent)
        messages.append({"role": "user", "content": prompt})

        # 8. 调用LLM
        try:
            print(f"[LLM Dynamic] Generating response with three-layer memory prompt...")

            if stream:
                return self._generate_streaming_response(messages)
            else:
                return self._generate_complete_response(messages)

        except Exception as e:
            print(f"[LLM Dynamic] Error: {e}")
            return self._fallback_chat_response(user_message, retrieved_emoji)

    def _build_user_prompt(
        self,
        user_message: str,
        retrieved_emoji: Optional[Dict[str, Any]],
        user_sent_emoji: bool,
        intent: Any = None
    ) -> str:
        """构建用户消息Prompt"""
        intent_hint = ""
        if intent:
            if intent.intent_type == "emotional":
                intent_hint = f"[检测到情绪: {intent.emotion or '表达情感'}] "
            elif intent.intent_type == "greeting":
                intent_hint = "[打招呼] "
            elif intent.intent_type == "farewell":
                intent_hint = "[告别] "

        if retrieved_emoji:
            emoji_desc = retrieved_emoji.get('description', '')
            emoji_category = retrieved_emoji.get('sub_category', '')

            if user_sent_emoji:
                return f"""{intent_hint}对方{user_message}

系统为你选择了一个表情包来回复：
- 表情描述：{emoji_desc}
- 类别：{emoji_category}

请自然地回复对方，可以用简短的文字配合表情包。表情包会随你的文字一起显示，不需要在文字中描述表情。"""
            else:
                return f"""{intent_hint}对方说："{user_message}"

系统会为你显示一个相关的表情包：
- 表情描述：{emoji_desc}
- 类别：{emoji_category}

请自然地回复对方。表情包会随你的文字一起显示，你不需要特别提及表情，也不要在回复中添加emoji字符。"""
        else:
            if user_sent_emoji:
                return f"{intent_hint}对方{user_message}\n\n请自然地回复对方的表情包。可以用简短、轻松的文字回复。"
            else:
                return f'{intent_hint}对方说："{user_message}"'

    def _generate_with_traditional_prompt(
        self,
        user_message: str,
        persona_id: int,
        session_id: Optional[int] = None,
        retrieved_emoji: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        use_memory: bool = True,
        use_similar_conversations: bool = True,
        stream: bool = False,
        user_sent_emoji: bool = False
    ):
        """传统Prompt生成方式（回退方案）"""
        # Get persona service and generate system prompt
        try:
            persona_service = self._get_persona_service()
            system_prompt = persona_service.generate_system_prompt(
                persona_id=persona_id,
                include_examples=use_similar_conversations,
                num_examples=3
            )
        except Exception as e:
            print(f"[LLM] Error generating persona prompt: {e}")
            system_prompt = self._get_default_system_prompt()

        # Get memory context if enabled
        memory_context = ""
        if use_memory and session_id:
            try:
                memory_service = self._get_memory_service()
                memory_context = memory_service.get_memory_context_for_chat(
                    persona_id=persona_id,
                    user_message=user_message,
                    max_memories=3
                )
            except Exception as e:
                print(f"[LLM] Error getting memory context: {e}")

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        # Add memory context as a system message if available
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-5:]:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", "")
                    })

        # Build current prompt with emoji context if available
        if retrieved_emoji:
            emoji_desc = retrieved_emoji.get('description', '')
            emoji_category = retrieved_emoji.get('sub_category', '')

            if user_sent_emoji:
                # 用户发送了表情包，我们也回复表情包
                prompt = f"""对方{user_message}

系统为你选择了一个表情包来回复：
- 表情描述：{emoji_desc}
- 类别：{emoji_category}

请自然地回复对方，可以用简短的文字配合表情包。表情包会随你的文字一起显示，不需要在文字中描述表情。"""
            else:
                prompt = f"""对方说："{user_message}"

系统会为你显示一个相关的表情包：
- 表情描述：{emoji_desc}
- 类别：{emoji_category}

请自然地回复对方。表情包会随你的文字一起显示，你不需要特别提及表情，也不要在回复中添加emoji字符。"""
        else:
            if user_sent_emoji:
                # 用户发送了表情包，但我们没有表情包回复
                prompt = f"""对方{user_message}

请自然地回复对方的表情包。可以用简短、轻松的文字回复。"""
            else:
                prompt = f'对方说："{user_message}"'

        messages.append({"role": "user", "content": prompt})
        
        try:
            print(f"[LLM] Generating personalized response for persona {persona_id}...")
            
            if stream:
                return self._generate_streaming_response(messages)
            else:
                return self._generate_complete_response(messages)
                
        except Exception as e:
            print(f"[LLM] Error generating personalized response: {type(e).__name__}: {e}")
            import traceback
            print(f"[LLM] Traceback: {traceback.format_exc()}")
            # 使用备用响应策略
            return self._fallback_chat_response(user_message, retrieved_emoji)
    
    def _generate_streaming_response(self, messages: List[Dict[str, str]]):
        """Generate a streaming response."""
        try:
            stream = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=0.7,
                max_tokens=200,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            print(f"[LLM] Error in streaming response: {e}")
            yield self._fallback_chat_response(
                messages[-1].get("content", ""), 
                None
            )
    
    def _generate_complete_response(self, messages: List[Dict[str, str]]) -> str:
        """Generate a complete (non-streaming) response."""
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=0.7,
            max_tokens=200
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # 避免 Windows 控制台编码问题
        try:
            print(f"[LLM] Generated response: {response_text[:100]}...")
        except UnicodeEncodeError:
            print(f"[LLM] Generated response: [contains emoji]")
        
        return response_text

    def generate_chat_response_stream(
        self,
        user_message: str,
        retrieved_emoji: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ):
        """Generate a streaming conversational response (legacy method)."""
        messages = [
            {
                "role": "system",
                "content": """You are a friendly chatbot assistant. Your personality is:
- Playful and engaging, but not overly formal
- Keep responses concise (1-2 sentences typically)
- Match the tone of the user's message
- IMPORTANT: Do NOT include any emoji characters (like 😊, 🎉, etc.) in your response. The system will automatically display appropriate images alongside your message."""
            }
        ]

        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-5:]:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", "")
                    })

        # Build current prompt with emoji context if available
        if retrieved_emoji:
            emoji_desc = retrieved_emoji.get('description', '')
            emoji_category = retrieved_emoji.get('sub_category', '')
            prompt = f"""User message: "{user_message}"

A relevant image will be displayed with your response:
- Image description: {emoji_desc}
- Category: {emoji_category}

Respond naturally to the user's message. The image will be shown alongside your text - do NOT mention the image explicitly and do NOT add any emoji characters to your response."""
        else:
            prompt = f'User message: "{user_message}"'

        messages.append({
            "role": "user",
            "content": prompt
        })

        try:
            print(f"[LLM] Generating streaming chat response...")

            stream = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=0.5,
                max_tokens=200,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            print(f"[LLM] Error generating streaming response: {type(e).__name__}: {e}")
            import traceback
            print(f"[LLM] Traceback: {traceback.format_exc()}")
            # 使用备用响应策略
            yield self._fallback_chat_response(user_message, retrieved_emoji)

    def generate_chat_response(
        self,
        user_message: str,
        retrieved_emoji: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Generate a conversational response to the user (non-streaming, legacy method)."""
        messages = [
            {
                "role": "system",
                "content": """You are a friendly chatbot assistant. Your personality is:
- Playful and engaging, but not overly formal
- Keep responses concise (1-2 sentences typically)
- Match the tone of the user's message
- IMPORTANT: Do NOT include any emoji characters (like 😊, 🎉, etc.) in your response. The system will automatically display appropriate images alongside your message."""
            }
        ]

        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-5:]:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", "")
                    })

        # Build current prompt with emoji context if available
        if retrieved_emoji:
            emoji_desc = retrieved_emoji.get('description', '')
            emoji_category = retrieved_emoji.get('sub_category', '')
            prompt = f"""User message: "{user_message}"

A relevant image will be displayed with your response:
- Image description: {emoji_desc}
- Category: {emoji_category}

Respond naturally to the user's message. The image will be shown alongside your text - do NOT mention the image explicitly and do NOT add any emoji characters to your response."""
        else:
            prompt = f'User message: "{user_message}"'

        messages.append({
            "role": "user",
            "content": prompt
        })

        try:
            print(f"[LLM] Generating chat response...")

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=0.5,
                max_tokens=200
            )

            response_text = response.choices[0].message.content.strip()
            # 避免 Windows 控制台编码问题
            try:
                print(f"[LLM] Generated response: {response_text[:100]}...")
            except UnicodeEncodeError:
                print(f"[LLM] Generated response: [contains emoji]")
            return response_text

        except Exception as e:
            print(f"[LLM] Error generating response: {type(e).__name__}: {e}")
            import traceback
            print(f"[LLM] Traceback: {traceback.format_exc()}")
            # 使用备用响应策略
            return self._fallback_chat_response(user_message, retrieved_emoji)

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt when persona is not available."""
        return """你是一个友好的AI助手。请用自然、亲切的方式回复用户。

重要提示：
- 不要在回复中包含emoji字符（如😊、😂等）
- 系统会根据你的回复自动推荐合适的表情包
- 保持回复简洁自然"""

    def _fallback_intent_analysis(self, user_message: str) -> IntentAnalysis:
        """当 LLM API 失败时的备用意图分析。"""
        message = user_message.lower()

        # 情感关键词
        emotion_keywords = [
            "开心", "高兴", "快乐", "兴奋", "爽", "棒", "赞", "哈哈", "嘿嘿", "嘻嘻",
            "难过", "伤心", "悲伤", "哭", "泪", "郁闷", "烦", "生气", "愤怒", "火大",
            "惊讶", "震惊", "哇", "天啊", "omg", "哦豁",
            "无语", "无奈", "尴尬", "呵呵", "汗",
            "累", "困", "饿", "渴", "冷", "热",
            "爱", "喜欢", "想", "思念", "抱", "亲", "么么哒"
        ]

        # 需要表情包的场景
        needs_emoji = any(keyword in message for keyword in emotion_keywords)

        # 生成搜索查询
        if needs_emoji:
            # 根据关键词生成搜索查询
            if any(k in message for k in ["开心", "高兴", "快乐", "哈哈"]):
                search_query = "开心 高兴 笑容 欢乐"
            elif any(k in message for k in ["难过", "伤心", "哭", "泪"]):
                search_query = "难过 伤心 哭泣 安慰"
            elif any(k in message for k in ["生气", "愤怒", "火大", "烦"]):
                search_query = "生气 愤怒 发火 不爽"
            elif any(k in message for k in ["惊讶", "震惊", "哇", "天啊"]):
                search_query = "惊讶 震惊 意外 哇"
            elif any(k in message for k in ["无语", "无奈", "尴尬", "呵呵"]):
                search_query = "无语 无奈 尴尬 汗颜"
            elif any(k in message for k in ["累", "困", "疲惫"]):
                search_query = "累 困 疲惫 睡觉"
            elif any(k in message for k in ["爱", "喜欢", "想", "抱", "亲"]):
                search_query = "爱 喜欢 抱抱 亲亲 爱心"
            else:
                search_query = user_message[:50]
        else:
            search_query = ""

        return IntentAnalysis(
            needs_emoji=needs_emoji,
            search_query=search_query,
            reasoning="Fallback analysis based on keyword matching"
        )

    def _fallback_chat_response(self, user_message: str, retrieved_emoji: Optional[Dict[str, Any]] = None) -> str:
        """当 LLM API 失败时的备用聊天响应。"""
        message = user_message.lower()

        # 简单的规则回复
        if any(k in message for k in ["你好", "嗨", "hi", "hello"]):
            return "你好呀！很高兴和你聊天~"
        elif any(k in message for k in ["谢谢", "感谢", "多谢"]):
            return "不客气！能帮到你我很开心~"
        elif any(k in message for k in ["再见", "拜拜", "bye"]):
            return "再见啦！随时来找我聊天哦~"
        elif any(k in message for k in ["哈哈", "嘿嘿", "嘻嘻"]):
            return "看到你开心我也开心！"
        elif any(k in message for k in ["难过", "伤心", "哭"]):
            return "抱抱你，别难过啦，一切都会好起来的~"
        elif any(k in message for k in ["累", "困", "疲惫"]):
            return "辛苦啦！好好休息一下吧~"
        elif retrieved_emoji:
            emoji_desc = retrieved_emoji.get('description', '')
            return f"{emoji_desc}！"
        else:
            return "嗯嗯，我在听呢，继续说~"

    def check_health(self) -> Dict[str, Any]:
        """Check the health status of the LLM service."""
        is_configured = bool(self.config.api_key)
        return {
            "configured": is_configured,
            "model": self.config.model,
            "base_url": self.config.base_url,
            "status": "healthy" if is_configured else "not_configured"
        }
