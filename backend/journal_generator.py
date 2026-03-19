"""
日记生成器 - AI驱动的对话总结

功能：
- 每日摘要自动生成
- 关键事件提取
- 偏好变化检测
- 情绪趋势分析
- 周记整合
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import Counter

from sqlalchemy.orm import Session

# 设置 HuggingFace 离线模式
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from database import (
    get_db, Memory, Persona, Message, ChatSession, TimelineJournal
)


class JournalGenerator:
    """日记生成器 - AI驱动的对话总结"""

    def __init__(self, db: Session = None, llm_service=None):
        self.db = db or get_db()
        self._llm_service = llm_service

    def _get_llm_service(self):
        """Lazy load LLM service."""
        if self._llm_service is None:
            from llm_service import LLMService
            self._llm_service = LLMService()
        return self._llm_service

    def generate_daily_summary(self, messages: List[Message], persona_id: int) -> Dict:
        """
        使用LLM生成每日摘要

        Args:
            messages: 当天的消息列表
            persona_id: Persona ID

        Returns:
            包含摘要、关键事件、偏好变化等的字典
        """
        if not messages:
            return {
                "summary": "今天没有对话记录",
                "key_events": [],
                "preference_changes": [],
                "mood_trend": "neutral",
                "topics": []
            }

        # 准备对话内容
        conversation_text = self._format_messages_for_summary(messages)

        # 尝试使用LLM生成摘要
        try:
            llm = self._get_llm_service()
            summary = self._generate_summary_with_llm(llm, conversation_text, "daily")
        except Exception as e:
            print(f"[JournalGenerator] LLM summary failed: {e}, using fallback")
            summary = self._generate_fallback_summary(messages)

        # 提取关键事件
        key_events = self.extract_key_events(messages)

        # 检测偏好变化
        preference_changes = self.detect_preference_changes(messages, persona_id)

        # 分析情绪趋势
        mood_trend = self.analyze_mood_trend(messages)

        # 提取讨论话题
        topics = self._extract_topics(messages)

        return {
            "summary": summary,
            "key_events": key_events,
            "preference_changes": preference_changes,
            "mood_trend": mood_trend,
            "topics": topics
        }

    def generate_weekly_summary(self, daily_journals: List[TimelineJournal], persona_id: int) -> Dict:
        """
        整合每日日记生成周记

        Args:
            daily_journals: 本周的每日日记列表
            persona_id: Persona ID

        Returns:
            包含周摘要、关键事件、偏好变化等的字典
        """
        if not daily_journals:
            return {
                "summary": "本周没有对话记录",
                "key_events": [],
                "preference_changes": [],
                "mood_trend": "neutral",
                "topics": []
            }

        # 合并每日摘要
        daily_summaries = [j.summary for j in daily_journals if j.summary]
        combined_text = "\n".join([f"- {s}" for s in daily_summaries])

        # 尝试使用LLM生成周摘要
        try:
            llm = self._get_llm_service()
            summary = self._generate_summary_with_llm(llm, combined_text, "weekly")
        except Exception as e:
            print(f"[JournalGenerator] LLM weekly summary failed: {e}, using fallback")
            summary = self._generate_fallback_weekly_summary(daily_journals)

        # 合并关键事件
        all_events = []
        for journal in daily_journals:
            if journal.key_events:
                all_events.extend(journal.key_events)

        # 去重并保留最重要的
        unique_events = self._deduplicate_events(all_events)[:10]

        # 合并偏好变化
        all_changes = []
        for journal in daily_journals:
            if journal.preference_changes:
                all_changes.extend(journal.preference_changes)

        unique_changes = self._deduplicate_preference_changes(all_changes)[:5]

        # 分析整体情绪趋势
        mood_trend = self._analyze_weekly_mood_trend(daily_journals)

        # 合并话题
        all_topics = []
        for journal in daily_journals:
            if journal.topics_discussed:
                all_topics.extend(journal.topics_discussed)

        topic_counts = Counter(all_topics)
        top_topics = [t for t, _ in topic_counts.most_common(5)]

        return {
            "summary": summary,
            "key_events": unique_events,
            "preference_changes": unique_changes,
            "mood_trend": mood_trend,
            "topics": top_topics
        }

    def extract_key_events(self, messages: List[Message]) -> List[Dict]:
        """
        提取关键事件

        识别对话中的重要事件，如：
        - 提到的计划/安排
        - 重要决定
        - 状态变化
        """
        events = []

        # 事件关键词模式
        event_patterns = [
            (r'明天(.+?)(?:[，。！]|$)', '计划', '明天'),
            (r'后天(.+?)(?:[，。！]|$)', '计划', '后天'),
            (r'下周(.+?)(?:[，。！]|$)', '计划', '下周'),
            (r'周末(.+?)(?:[，。！]|$)', '计划', '周末'),
            (r'今晚(.+?)(?:[，。！]|$)', '安排', '今晚'),
            (r'决定(.+?)(?:[，。！]|$)', '决定', ''),
            (r'要去(.+?)(?:[，。！]|$)', '计划', ''),
            (r'买了(.+?)(?:[，。！]|$)', '购买', ''),
        ]

        for msg in messages:
            if msg.role != 'user':
                continue

            content = msg.content

            for pattern, event_type, time_prefix in event_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        match = next((m for m in match if m), '')

                    if match:
                        event_text = f"{time_prefix}{match}" if time_prefix else match
                        events.append({
                            "type": event_type,
                            "content": event_text,
                            "time": msg.created_at.isoformat() if msg.created_at else None
                        })

        # 去重
        unique_events = []
        seen_contents = set()

        for event in events:
            content_key = event["content"][:20]  # 使用前20字符去重
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                unique_events.append(event)

        return unique_events[:10]  # 最多返回10个事件

    def detect_preference_changes(self, messages: List[Message], persona_id: int) -> List[Dict]:
        """
        检测偏好变化

        识别可能表示偏好变化的对话，如：
        - 新的喜欢/不喜欢
        - 改变的观点
        - 新的兴趣
        """
        changes = []

        # 偏好变化模式
        preference_patterns = [
            (r'我喜欢(.+?)(?:[，。！]|$)', '喜欢', 'new_preference'),
            (r'我爱(.+?)(?:[，。！]|$)', '喜欢', 'new_preference'),
            (r'我不喜欢(.+?)(?:[，。！]|$)', '不喜欢', 'new_preference'),
            (r'我讨厌(.+?)(?:[，。！]|$)', '不喜欢', 'new_preference'),
            (r'最近迷上(.+?)(?:[，。！]|$)', '新兴趣', 'new_interest'),
            (r'开始(.+?)(?:[，。！]|$)', '新习惯', 'new_habit'),
            (r'不再(.+?)(?:[，。！]|$)', '改变', 'preference_change'),
        ]

        for msg in messages:
            if msg.role != 'user':
                continue

            content = msg.content

            for pattern, change_type, change_category in preference_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        match = next((m for m in match if m), '')

                    if match:
                        # 检查是否是新的偏好
                        existing = self.db.query(Memory).filter(
                            Memory.persona_id == persona_id,
                            Memory.memory_type == "preference",
                            Memory.content.contains(match)
                        ).first()

                        is_new = existing is None

                        changes.append({
                            "type": change_type,
                            "content": match,
                            "category": change_category,
                            "is_new": is_new,
                            "time": msg.created_at.isoformat() if msg.created_at else None
                        })

        return changes[:5]  # 最多返回5个变化

    def analyze_mood_trend(self, messages: List[Message]) -> str:
        """
        分析情绪趋势

        Returns:
            情绪趋势: positive, negative, neutral, mixed
        """
        if not messages:
            return "neutral"

        # 情绪关键词
        positive_keywords = [
            "开心", "高兴", "快乐", "兴奋", "爽", "棒", "赞", "哈哈", "嘿嘿", "嘻嘻",
            "幸福", "满足", "喜欢", "爱", "好", "太好了", "完美"
        ]

        negative_keywords = [
            "难过", "伤心", "悲伤", "哭", "泪", "郁闷", "烦", "生气", "愤怒", "火大",
            "累", "疲惫", "无聊", "无语", "糟糕", "烦人"
        ]

        positive_count = 0
        negative_count = 0

        for msg in messages:
            if msg.role != 'user':
                continue

            content = msg.content.lower()

            for keyword in positive_keywords:
                if keyword in content:
                    positive_count += 1

            for keyword in negative_keywords:
                if keyword in content:
                    negative_count += 1

        # 计算趋势
        total = positive_count + negative_count

        if total == 0:
            return "neutral"

        positive_ratio = positive_count / total

        if positive_ratio > 0.6:
            return "positive"
        elif positive_ratio < 0.4:
            return "negative"
        elif positive_count > 0 and negative_count > 0:
            return "mixed"
        else:
            return "neutral"

    def _format_messages_for_summary(self, messages: List[Message]) -> str:
        """格式化消息用于摘要生成"""
        parts = []

        for msg in messages[-20:]:  # 最多取最近20条
            role = "用户" if msg.role == "user" else "助手"
            content = msg.content[:100]  # 截断长消息
            parts.append(f"{role}：{content}")

        return "\n".join(parts)

    def _generate_summary_with_llm(self, llm, conversation_text: str, summary_type: str) -> str:
        """使用LLM生成摘要（带超时控制和错误处理）"""
        if summary_type == "daily":
            prompt = f"""请为以下对话生成一个简洁的每日摘要（50字以内）：

{conversation_text}

摘要应包括：
1. 主要讨论话题
2. 用户情绪状态
3. 任何重要事件

请直接输出摘要，不要包含其他内容。"""
        else:  # weekly
            prompt = f"""请为以下每日摘要生成一个周总结（100字以内）：

{conversation_text}

周总结应包括：
1. 本周主要活动
2. 情绪变化趋势
3. 值得关注的偏好变化

请直接输出总结，不要包含其他内容。"""

        try:
            # 使用已配置超时的LLM客户端
            # 超时配置在LLMService.__init__中完成
            response = llm.client.chat.completions.create(
                model=llm.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=150,
                timeout=10.0  # 额外的请求级超时保护
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            # 捕获所有异常，包括超时、网络错误等
            error_type = type(e).__name__
            print(f"[JournalGenerator] LLM error ({error_type}): {e}")
            raise

    def _generate_fallback_summary(self, messages: List[Message]) -> str:
        """生成备用摘要（不依赖LLM）"""
        user_messages = [m for m in messages if m.role == "user"]

        if not user_messages:
            return "今天没有用户消息"

        # 提取关键词
        all_content = " ".join([m.content for m in user_messages])
        keywords = self._extract_simple_keywords(all_content)

        # 分析情绪
        mood = self.analyze_mood_trend(messages)
        mood_map = {
            "positive": "情绪积极",
            "negative": "情绪有些低落",
            "mixed": "情绪起伏",
            "neutral": "情绪平稳"
        }

        # 统计消息数量
        msg_count = len(user_messages)

        summary = f"今天共{msg_count}条消息，{mood_map.get(mood, '情绪平稳')}"

        if keywords:
            summary += f"，主要聊了{keywords[:3]}等话题"

        return summary

    def _generate_fallback_weekly_summary(self, daily_journals: List[TimelineJournal]) -> str:
        """生成备用周摘要"""
        total_messages = sum(j.message_count for j in daily_journals)
        journal_count = len(daily_journals)

        # 统计情绪趋势
        mood_counts = Counter(j.mood_trend for j in daily_journals if j.mood_trend)
        dominant_mood = mood_counts.most_common(1)[0][0] if mood_counts else "neutral"

        mood_map = {
            "positive": "整体心情愉快",
            "negative": "有些烦恼",
            "mixed": "情绪有起伏",
            "neutral": "情绪平稳"
        }

        summary = f"本周{journal_count}天有对话，共{total_messages}条消息，{mood_map.get(dominant_mood, '情绪平稳')}"

        # 提取主要话题
        all_topics = []
        for j in daily_journals:
            if j.topics_discussed:
                all_topics.extend(j.topics_discussed)

        if all_topics:
            topic_counts = Counter(all_topics)
            top_topics = [t for t, _ in topic_counts.most_common(3)]
            summary += f"，主要话题：{top_topics}"

        return summary

    def _extract_topics(self, messages: List[Message]) -> List[str]:
        """提取讨论话题"""
        topics = []

        # 话题指示词
        topic_patterns = [
            r'关于(.+?)[，。！]',
            r'(.+?)怎么样',
            r'(.+?)好吗',
            r'我觉得(.+?)',
            r'说起来(.+?)[，。！]',
        ]

        for msg in messages:
            if msg.role != 'user':
                continue

            for pattern in topic_patterns:
                matches = re.findall(pattern, msg.content)
                for match in matches:
                    if isinstance(match, tuple):
                        match = next((m for m in match if m), '')

                    if match and len(match) > 1:
                        topics.append(match.strip())

        # 去重并统计
        topic_counts = Counter(topics)
        return [t for t, _ in topic_counts.most_common(10)]

    def _extract_simple_keywords(self, text: str) -> List[str]:
        """简单关键词提取"""
        # 停用词
        stop_words = {'的', '了', '是', '我', '你', '在', '有', '个', '吗', '吧', '呢', '啊', '和', '就', '都', '要', '这', '那'}

        keywords = []

        # 提取2-gram
        for i in range(len(text) - 1):
            word = text[i:i+2]
            if word not in stop_words and not any(c in word for c in '，。！？、'):
                keywords.append(word)

        # 统计频率
        word_counts = Counter(keywords)
        return [w for w, _ in word_counts.most_common(5)]

    def _deduplicate_events(self, events: List[Dict]) -> List[Dict]:
        """去重事件"""
        seen = set()
        unique = []

        for event in events:
            key = event.get("content", "")[:20]
            if key not in seen:
                seen.add(key)
                unique.append(event)

        return unique

    def _deduplicate_preference_changes(self, changes: List[Dict]) -> List[Dict]:
        """去重偏好变化"""
        seen = set()
        unique = []

        for change in changes:
            key = f"{change.get('type')}:{change.get('content', '')[:15]}"
            if key not in seen:
                seen.add(key)
                unique.append(change)

        return unique

    def _analyze_weekly_mood_trend(self, daily_journals: List[TimelineJournal]) -> str:
        """分析周情绪趋势"""
        moods = [j.mood_trend for j in daily_journals if j.mood_trend]

        if not moods:
            return "neutral"

        mood_counts = Counter(moods)

        # 检查是否有明显趋势
        positive = mood_counts.get("positive", 0)
        negative = mood_counts.get("negative", 0)

        if positive > negative + 2:
            return "positive"
        elif negative > positive + 2:
            return "negative"
        elif positive > 0 and negative > 0:
            return "mixed"
        else:
            return mood_counts.most_common(1)[0][0]


# Singleton
_journal_generator = None


def get_journal_generator(db: Session = None) -> JournalGenerator:
    """Get or create journal generator singleton."""
    global _journal_generator
    if _journal_generator is None:
        _journal_generator = JournalGenerator(db)
    return _journal_generator


if __name__ == "__main__":
    from database import init_database
    init_database()

    generator = get_journal_generator()

    # 测试情绪分析
    test_messages = [
        Message(role="user", content="今天好开心啊！哈哈"),
        Message(role="assistant", content="太棒了！"),
        Message(role="user", content="有点累了"),
        Message(role="assistant", content="好好休息"),
    ]

    mood = generator.analyze_mood_trend(test_messages)
    print(f"Mood trend: {mood}")

    # 测试事件提取
    events = generator.extract_key_events([
        Message(role="user", content="明天要去开会"),
        Message(role="user", content="周末打算看电影"),
    ])
    print(f"Events: {events}")

    print("\n[JournalGenerator] Service initialized successfully")