"""
动态Prompt服务 - 实现三种动态适应机制

1. 语义化记忆检索 (SemanticMemoryRetriever)
   - 基于向量相似度检索相关记忆
   - 替代简单的关键词匹配

2. 意图感知模板选择 (IntentAwarePromptBuilder)
   - 根据对话意图动态选择Prompt模板
   - 支持情感、信息、闲聊等场景

3. 持续学习机制 (ContinuousPersonaLearner)
   - 从记忆中持续更新Persona特征
   - 检测用户偏好漂移
   - 自动发现新的口头禅和习惯
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter
from dataclasses import dataclass

import numpy as np

# 设置离线模式
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# 尝试导入向量编码器
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("[DynamicPrompt] Warning: sentence-transformers not available")

from sqlalchemy.orm import Session
from database import get_db, Memory, Persona, ChatHistory


# ==================== 1. 语义化记忆检索 ====================

class SemanticMemoryRetriever:
    """
    语义化记忆检索器

    使用向量编码器计算查询与记忆的语义相似度，
    替代传统的关键词匹配方法。

    优势：
    - 理解语义相似性（"喜欢跑步" 和 "爱运动" 匹配度高）
    - 支持模糊匹配
    - 多语言支持
    """

    def __init__(self, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        self.model_name = model_name
        self.encoder = None
        self._init_encoder()

    def _init_encoder(self):
        """初始化向量编码器"""
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.encoder = SentenceTransformer(self.model_name)
                print(f"[SemanticMemory] Loaded encoder: {self.model_name}")
            except Exception as e:
                print(f"[SemanticMemory] Error loading encoder: {e}")
                self.encoder = None

    def encode(self, text: str) -> Optional[np.ndarray]:
        """将文本编码为向量"""
        if self.encoder is None:
            return None
        try:
            return self.encoder.encode(text, convert_to_numpy=True)
        except Exception as e:
            print(f"[SemanticMemory] Encoding error: {e}")
            return None

    def compute_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        if vec1 is None or vec2 is None:
            return 0.0
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

    def retrieve_memories(
        self,
        query: str,
        memories: List[Memory],
        top_k: int = 5,
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        检索与查询语义相关的记忆

        Args:
            query: 用户输入
            memories: 记忆列表
            top_k: 返回数量
            threshold: 相似度阈值

        Returns:
            排序后的相关记忆列表
        """
        if not memories:
            return []

        # 如果编码器不可用，回退到关键词匹配
        if self.encoder is None:
            return self._fallback_retrieve(query, memories, top_k)

        # 编码查询
        query_embedding = self.encode(query)
        if query_embedding is None:
            return self._fallback_retrieve(query, memories, top_k)

        # 计算每条记忆的相似度
        scored_memories = []
        for memory in memories:
            # 编码记忆内容
            memory_text = f"{memory.content} {memory.context or ''}"
            memory_embedding = self.encode(memory_text)

            if memory_embedding is not None:
                similarity = self.compute_similarity(query_embedding, memory_embedding)

                # 综合考虑：语义相似度 + 重要性 + 时效性
                importance = memory.importance_score or 0.5

                # 时效性加成（最近访问的记忆略微提升）
                recency_boost = 0
                if memory.last_accessed:
                    days_ago = (datetime.utcnow() - memory.last_accessed).days
                    if days_ago < 7:
                        recency_boost = 0.1 * (7 - days_ago) / 7

                final_score = similarity * 0.6 + importance * 0.3 + recency_boost

                if final_score >= threshold:
                    scored_memories.append({
                        'memory': memory,
                        'similarity': similarity,
                        'final_score': final_score
                    })

        # 按分数排序
        scored_memories.sort(key=lambda x: x['final_score'], reverse=True)

        # 返回top_k
        results = []
        for item in scored_memories[:top_k]:
            memory = item['memory']
            results.append({
                'id': memory.id,
                'content': memory.content,
                'type': memory.memory_type,
                'importance': memory.importance_score,
                'similarity': round(item['similarity'], 3),
                'final_score': round(item['final_score'], 3)
            })

        return results

    def _fallback_retrieve(
        self,
        query: str,
        memories: List[Memory],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """关键词匹配回退方案"""
        # 提取关键词
        keywords = self._extract_keywords(query)

        scored = []
        for memory in memories:
            memory_text = f"{memory.content} {memory.context or ''}"
            score = sum(1 for kw in keywords if kw in memory_text)
            score += (memory.importance_score or 0.5) * 0.5

            if score > 0:
                scored.append({
                    'memory': memory,
                    'score': score
                })

        scored.sort(key=lambda x: x['score'], reverse=True)

        return [
            {
                'id': item['memory'].id,
                'content': item['memory'].content,
                'type': item['memory'].memory_type,
                'importance': item['memory'].importance_score,
                'similarity': 0.0,
                'final_score': item['score']
            }
            for item in scored[:top_k]
        ]

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        stop_words = {'的', '了', '是', '我', '你', '在', '有', '个', '吗', '吧', '呢', '啊'}
        keywords = []
        # 2-gram
        for i in range(len(text) - 1):
            bigram = text[i:i+2]
            if bigram not in stop_words:
                keywords.append(bigram)
        return list(set(keywords))[:15]


# ==================== 2. 意图感知模板选择 ====================

@dataclass
class IntentResult:
    """意图识别结果"""
    intent_type: str  # emotional, informational, casual, greeting, farewell
    confidence: float
    emotion: Optional[str] = None
    topics: List[str] = None


class IntentAwarePromptBuilder:
    """
    意图感知的Prompt构建器

    根据对话意图动态选择和调整Prompt模板，
    实现更精准的风格控制和回应策略。

    支持的意图类型：
    - emotional: 情感表达（需要共情）
    - informational: 信息询问（需要准确）
    - casual: 闲聊（轻松自然）
    - greeting: 问候（热情回应）
    - farewell: 告别（温暖送别）
    """

    # 意图关键词映射
    INTENT_KEYWORDS = {
        "emotional": {
            "positive": ["开心", "高兴", "快乐", "兴奋", "哈哈", "嘿嘿", "太棒了", "好耶"],
            "negative": ["难过", "伤心", "哭", "烦", "累", "郁闷", "不开心", "崩溃"],
            "anxious": ["紧张", "担心", "害怕", "焦虑", "不安"],
            "surprised": ["哇", "天哪", "震惊", "意外", "不敢相信"],
        },
        "informational": ["是什么", "怎么", "为什么", "多少", "哪里", "什么时候", "如何", "吗", "？"],
        "greeting": ["你好", "嗨", "hi", "hello", "早上好", "晚上好", "在吗"],
        "farewell": ["再见", "拜拜", "bye", "走了", "先忙", "晚安"],
        "casual": []  # 默认类型
    }

    # 场景特定Prompt模板
    INTENT_TEMPLATES = {
        "emotional": """
【情感对话指导】
对方正在表达情绪，请遵循以下原则：
1. 首先共情，理解对方的感受
2. 用温暖的语言回应，避免说教
3. 可以分享相似经历拉近距离
4. 检测到的情绪：{emotion}

记忆上下文：
{memory_context}

请用{style}的语气回应，记住你是{persona_name}的数字孪生。
""",
        "informational": """
【信息查询指导】
对方在询问信息，请遵循以下原则：
1. 提供准确、有帮助的回答
2. 如果不确定，诚实说明
3. 可以补充相关信息

相关记忆：
{memory_context}

请用简洁清晰的方式回答，保持{style}的风格。
""",
        "greeting": """
【问候回应】
对方在打招呼，请热情回应！
可以用一些口头禅让回应更自然，比如：{catchphrases}

保持{style}的语气，展现{persona_name}的个性。
""",
        "farewell": """
【告别回应】
对方要离开了，请温暖送别。
可以说一些期待下次聊天的话。

保持{style}的语气。
""",
        "casual": """
【日常闲聊】
这是一次轻松的日常对话。
{memory_context}

保持{style}的语气，像老朋友一样聊天。
记住你的说话风格：{style_hints}
"""
    }

    def classify_intent(self, user_message: str) -> IntentResult:
        """
        分类用户意图

        Args:
            user_message: 用户消息

        Returns:
            IntentResult: 意图识别结果
        """
        message = user_message.lower()

        # 检查问候
        for kw in self.INTENT_KEYWORDS["greeting"]:
            if kw in message:
                return IntentResult(
                    intent_type="greeting",
                    confidence=0.9
                )

        # 检查告别
        for kw in self.INTENT_KEYWORDS["farewell"]:
            if kw in message:
                return IntentResult(
                    intent_type="farewell",
                    confidence=0.9
                )

        # 检查情感表达
        for emotion, keywords in self.INTENT_KEYWORDS["emotional"].items():
            for kw in keywords:
                if kw in message:
                    return IntentResult(
                        intent_type="emotional",
                        confidence=0.8,
                        emotion=emotion
                    )

        # 检查信息查询
        info_score = sum(1 for kw in self.INTENT_KEYWORDS["informational"] if kw in message)
        if info_score >= 1:
            return IntentResult(
                intent_type="informational",
                confidence=0.7,
                topics=self._extract_topics(message)
            )

        # 默认为闲聊
        return IntentResult(
            intent_type="casual",
            confidence=0.5,
            topics=self._extract_topics(message)
        )

    def build_prompt(
        self,
        intent: IntentResult,
        persona: Persona,
        memory_context: str = "",
        examples: List[Dict] = None
    ) -> str:
        """
        根据意图构建Prompt

        Args:
            intent: 意图识别结果
            persona: 角色信息
            memory_context: 记忆上下文
            examples: 对话示例

        Returns:
            构建好的Prompt
        """
        # 获取模板
        template = self.INTENT_TEMPLATES.get(intent.intent_type, self.INTENT_TEMPLATES["casual"])

        # 准备填充参数
        style = self._get_style_description(persona.response_style)
        catchphrases = ", ".join(persona.common_phrases[:3]) if persona.common_phrases else "哈哈, 嗯嗯"

        # 格式化模板
        prompt = template.format(
            emotion=intent.emotion or "未检测到",
            memory_context=memory_context or "暂无相关记忆",
            style=style,
            persona_name=persona.name,
            catchphrases=catchphrases,
            style_hints=self._get_style_hints(persona),
            topics=", ".join(intent.topics) if intent.topics else ""
        )

        # 添加对话示例
        if examples:
            prompt += "\n\n参考对话示例：\n"
            for i, ex in enumerate(examples[:3], 1):
                prompt += f"示例{i}：\n"
                prompt += f"对方：{ex.get('user_message', '')}\n"
                prompt += f"你：{ex.get('assistant_response', '')}\n"

        return prompt

    def _get_style_description(self, style: str) -> str:
        """获取风格描述"""
        style_map = {
            "formal": "正式、礼貌",
            "casual": "随意自然",
            "humorous": "幽默风趣",
            "warm": "温暖亲切",
            "professional": "专业严谨"
        }
        return style_map.get(style, "自然亲切")

    def _get_style_hints(self, persona: Persona) -> str:
        """获取风格提示"""
        hints = []

        traits = persona.personality_traits or {}
        if traits.get("formality", 0.5) > 0.7:
            hints.append("说话较正式")
        elif traits.get("formality", 0.5) < 0.3:
            hints.append("说话随意亲切")

        if traits.get("humor", 0.5) > 0.6:
            hints.append("喜欢开玩笑")

        if traits.get("warmth", 0.5) > 0.6:
            hints.append("语气温暖")

        return "、".join(hints) if hints else "保持自然"

    def _extract_topics(self, text: str) -> List[str]:
        """提取话题"""
        # 简单的话题提取
        topics = []
        topic_patterns = [
            r'关于(.{2,10})',
            r'(.{2,8})怎么样',
        ]
        for pattern in topic_patterns:
            matches = re.findall(pattern, text)
            topics.extend(matches)
        return list(set(topics))[:3]


# ==================== 3. 持续学习机制 ====================

class ContinuousPersonaLearner:
    """
    持续学习的Persona更新器

    从对话记忆中持续学习和更新Persona特征：
    1. 口头禅发现 - 自动发现新的常用表达
    2. 偏好漂移检测 - 检测用户偏好的变化趋势
    3. 性格特征更新 - 基于行为模式更新性格特征
    4. 表情习惯学习 - 更新表情包使用习惯
    """

    # 口头禅模式
    CATCHPHRASE_PATTERNS = [
        r'(哈哈|嘿嘿|嘻嘻|呵呵|嗯嗯|好的|好哒|没问题|可以呀|行啊)',
        r'(呀|呢|吧|嘛|啦|咯|哒)[。！~]',
        r'(~+|…+)',
    ]

    def __init__(self, db: Session = None):
        self.db = db or get_db()

    def learn_from_memories(self, persona_id: int) -> Dict[str, Any]:
        """
        从记忆中学习并更新Persona

        Args:
            persona_id: Persona ID

        Returns:
            学习结果和更新内容
        """
        persona = self.db.query(Persona).filter(Persona.id == persona_id).first()
        if not persona:
            return {"error": "Persona not found"}

        # 获取所有记忆
        memories = self.db.query(Memory).filter(
            Memory.persona_id == persona_id
        ).order_by(Memory.created_at.desc()).limit(100).all()

        # 获取聊天历史
        chat_histories = self.db.query(ChatHistory).filter(
            ChatHistory.persona_id == persona_id
        ).order_by(ChatHistory.imported_at.desc()).limit(50).all()

        updates = {}

        # 1. 发现新的口头禅
        new_catchphrases = self._discover_catchphrases(chat_histories)
        if new_catchphrases:
            updates['new_catchphrases'] = new_catchphrases

        # 2. 检测偏好漂移
        preference_drift = self._detect_preference_drift(memories)
        if preference_drift:
            updates['preference_drift'] = preference_drift

        # 3. 更新性格特征
        trait_updates = self._update_personality_traits(memories, persona)
        if trait_updates:
            updates['trait_updates'] = trait_updates

        # 4. 更新表情包习惯
        emoji_updates = self._update_emoji_behavior(chat_histories, persona)
        if emoji_updates:
            updates['emoji_updates'] = emoji_updates

        return {
            "persona_id": persona_id,
            "updates": updates,
            "learned_at": datetime.utcnow().isoformat()
        }

    def _discover_catchphrases(self, chat_histories: List[ChatHistory]) -> List[str]:
        """
        从对话历史中发现口头禅

        原理：统计高频出现且非通用的表达模式
        """
        if not chat_histories:
            return []

        # 收集所有回复
        responses = [h.assistant_response for h in chat_histories if h.assistant_response]

        # 统计模式出现频率
        pattern_counts = Counter()
        for response in responses:
            for pattern in self.CATCHPHRASE_PATTERNS:
                matches = re.findall(pattern, response)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    pattern_counts[match] += 1

        # 筛选高频模式（出现率 > 20%）
        total = len(responses)
        catchphrases = []
        for pattern, count in pattern_counts.most_common(10):
            if count / total > 0.2:
                catchphrases.append(pattern)

        return catchphrases[:5]

    def _detect_preference_drift(self, memories: List[Memory]) -> Optional[Dict]:
        """
        检测偏好漂移

        分析记忆中的偏好变化趋势
        """
        if len(memories) < 5:
            return None

        # 按时间分组
        recent = [m for m in memories if m.created_at and
                  (datetime.utcnow() - m.created_at).days < 30]
        older = [m for m in memories if m.created_at and
                 (datetime.utcnow() - m.created_at).days >= 30]

        if not recent or not older:
            return None

        # 比较偏好类型分布
        def get_preference_distribution(mem_list):
            prefs = [m for m in mem_list if m.memory_type == 'preference']
            dist = Counter()
            for p in prefs:
                if '喜欢' in p.content:
                    dist['like'] += 1
                elif '不喜欢' in p.content:
                    dist['dislike'] += 1
            return dist

        recent_dist = get_preference_distribution(recent)
        older_dist = get_preference_distribution(older)

        # 检测显著变化
        drift = {}
        if recent_dist['like'] > older_dist['like'] * 1.5:
            drift['trend'] = 'more_positive'
            drift['description'] = '用户近期表达了更多正面偏好'
        elif recent_dist['dislike'] > older_dist['dislike'] * 1.5:
            drift['trend'] = 'more_negative'
            drift['description'] = '用户近期表达了更多负面偏好'

        return drift if drift else None

    def _update_personality_traits(
        self,
        memories: List[Memory],
        persona: Persona
    ) -> Optional[Dict]:
        """
        更新性格特征

        基于记忆内容分析性格倾向
        """
        if not memories:
            return None

        traits = persona.personality_traits or {}
        updates = {}

        # 分析情感倾向 -> warmth
        emotional_memories = [m for m in memories if m.memory_type == 'preference']
        positive_count = sum(1 for m in emotional_memories if '喜欢' in m.content or '爱' in m.content)
        negative_count = sum(1 for m in emotional_memories if '不喜欢' in m.content or '讨厌' in m.content)

        if emotional_memories:
            warmth = traits.get('warmth', 0.5)
            # 正面偏好多 -> warmth 略微提升
            if positive_count > negative_count * 2:
                warmth = min(0.9, warmth + 0.05)
            elif negative_count > positive_count * 2:
                warmth = max(0.1, warmth - 0.05)
            if abs(warmth - traits.get('warmth', 0.5)) > 0.01:
                updates['warmth'] = warmth

        return updates if updates else None

    def _update_emoji_behavior(
        self,
        chat_histories: List[ChatHistory],
        persona: Persona
    ) -> Optional[Dict]:
        """
        更新表情包使用行为

        从对话中学习表情包使用习惯
        """
        if not chat_histories:
            return None

        # 统计表情包使用
        emoji_pattern = r'\[表情[：:].+?\]'
        emoji_count = 0
        total = len(chat_histories)

        scenarios = []
        for history in chat_histories:
            if re.search(emoji_pattern, history.assistant_response):
                emoji_count += 1
                # 分析使用场景
                user_msg = history.user_message.lower()
                if any(kw in user_msg for kw in ['哈哈', '开心', '高兴', '笑']):
                    scenarios.append('开心')
                elif any(kw in user_msg for kw in ['难过', '伤心', '哭']):
                    scenarios.append('安慰')
                elif any(kw in user_msg for kw in ['无语', '服了', '晕']):
                    scenarios.append('无奈')

        usage_rate = emoji_count / total if total > 0 else 0

        updates = {}

        # 更新使用率
        current_rate = persona.emoji_usage_rate or 0.5
        if abs(usage_rate - current_rate) > 0.1:
            updates['usage_rate'] = usage_rate

        # 更新使用频率级别
        if usage_rate == 0:
            new_frequency = "none"
        elif usage_rate < 0.2:
            new_frequency = "low"
        elif usage_rate < 0.5:
            new_frequency = "medium"
        else:
            new_frequency = "high"

        if new_frequency != persona.emoji_usage_frequency:
            updates['frequency'] = new_frequency

        # 更新场景偏好
        if scenarios:
            scenario_counter = Counter(scenarios)
            new_scenarios = [s for s, _ in scenario_counter.most_common(3)]
            if new_scenarios != (persona.emoji_scenario_prefs or []):
                updates['scenarios'] = new_scenarios

        return updates if updates else None

    def apply_updates(self, persona_id: int, updates: Dict) -> bool:
        """
        应用学习结果到Persona

        Args:
            persona_id: Persona ID
            updates: 更新内容

        Returns:
            是否更新成功
        """
        persona = self.db.query(Persona).filter(Persona.id == persona_id).first()
        if not persona:
            return False

        # 更新口头禅
        if 'new_catchphrases' in updates:
            current = persona.common_phrases or []
            new_phrases = updates['new_catchphrases']
            # 合并新旧口头禅，保留最新的
            combined = list(dict.fromkeys(new_phrases + current))[:10]
            persona.common_phrases = combined

        # 更新性格特征
        if 'trait_updates' in updates:
            traits = persona.personality_traits or {}
            traits.update(updates['trait_updates'])
            persona.personality_traits = traits

        # 更新表情包行为
        if 'emoji_updates' in updates:
            emoji_updates = updates['emoji_updates']
            if 'usage_rate' in emoji_updates:
                persona.emoji_usage_rate = emoji_updates['usage_rate']
            if 'frequency' in emoji_updates:
                persona.emoji_usage_frequency = emoji_updates['frequency']
            if 'scenarios' in emoji_updates:
                persona.emoji_scenario_prefs = emoji_updates['scenarios']

        persona.updated_at = datetime.utcnow()
        self.db.commit()

        print(f"[ContinuousLearner] Updated persona {persona_id}")
        return True


# ==================== 统一服务入口 ====================

class DynamicPromptService:
    """
    动态Prompt服务 - 统一管理三种适应机制

    使用方式：
    ```python
    service = DynamicPromptService()

    # 1. 检索相关记忆
    memories = service.retrieve_memories(persona_id, user_message)

    # 2. 识别意图并构建Prompt
    intent = service.classify_intent(user_message)
    prompt = service.build_dynamic_prompt(intent, persona, memories)

    # 3. 持续学习
    service.learn_and_update(persona_id)
    ```
    """

    def __init__(self, db: Session = None):
        self.db = db or get_db()
        self.memory_retriever = SemanticMemoryRetriever()
        self.prompt_builder = IntentAwarePromptBuilder()
        self.learner = ContinuousPersonaLearner(self.db)

    def retrieve_memories(
        self,
        persona_id: int,
        query: str,
        top_k: int = 5
    ) -> List[Dict]:
        """语义化记忆检索"""
        memories = self.db.query(Memory).filter(
            Memory.persona_id == persona_id
        ).order_by(Memory.importance_score.desc()).limit(50).all()

        return self.memory_retriever.retrieve_memories(query, memories, top_k)

    def classify_intent(self, user_message: str) -> IntentResult:
        """意图识别"""
        return self.prompt_builder.classify_intent(user_message)

    def build_dynamic_prompt(
        self,
        intent: IntentResult,
        persona: Persona,
        memories: List[Dict] = None,
        examples: List[Dict] = None
    ) -> str:
        """构建动态Prompt"""
        # 格式化记忆上下文
        memory_context = ""
        if memories:
            memory_context = "\n".join([f"- {m['content']}" for m in memories[:3]])

        return self.prompt_builder.build_prompt(
            intent=intent,
            persona=persona,
            memory_context=memory_context,
            examples=examples
        )

    def learn_and_update(self, persona_id: int) -> Dict:
        """持续学习并更新Persona"""
        result = self.learner.learn_from_memories(persona_id)

        if 'updates' in result and result['updates']:
            self.learner.apply_updates(persona_id, result['updates'])

        return result

    def get_memory_context_string(self, memories: List[Dict]) -> str:
        """获取格式化的记忆上下文字符串"""
        if not memories:
            return ""

        parts = ["关于用户的相关记忆："]
        for m in memories:
            similarity = m.get('similarity', 0)
            if similarity > 0:
                parts.append(f"- {m['content']} (相关度: {similarity:.2f})")
            else:
                parts.append(f"- {m['content']}")

        return "\n".join(parts)


# 单例
_dynamic_prompt_service = None

def get_dynamic_prompt_service(db: Session = None) -> DynamicPromptService:
    """获取动态Prompt服务单例"""
    global _dynamic_prompt_service
    if _dynamic_prompt_service is None:
        _dynamic_prompt_service = DynamicPromptService(db)
    return _dynamic_prompt_service


if __name__ == "__main__":
    # 测试
    from database import init_database
    init_database()

    service = get_dynamic_prompt_service()

    # 测试意图识别
    test_messages = [
        "我今天好开心啊！",
        "请问这个怎么用？",
        "你好！",
        "再见啦",
        "周末一起吃饭吧"
    ]

    print("=== 意图识别测试 ===")
    for msg in test_messages:
        intent = service.classify_intent(msg)
        print(f"消息: {msg}")
        print(f"  意图: {intent.intent_type}, 情绪: {intent.emotion}")
        print()