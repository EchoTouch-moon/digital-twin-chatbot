"""
Memory Service for Digital Twin Chatbot.

This service manages long-term memory about users, including:
- User preferences
- Important facts
- Relationship history
- Conversation context
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import Counter

from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, Memory, Message, ChatSession, Persona


class MemoryService:
    """Service for managing long-term memories."""
    
    # Memory types
    TYPE_FACT = "fact"
    TYPE_PREFERENCE = "preference"
    TYPE_EVENT = "event"
    TYPE_RELATIONSHIP = "relationship"
    TYPE_TOPIC = "topic"
    
    def __init__(self, db: Session = None):
        self.db = db or get_db()
    
    def create_memory(
        self,
        persona_id: int,
        content: str,
        memory_type: str = TYPE_FACT,
        source_message_id: int = None,
        context: str = None,
        importance: float = 1.0
    ) -> Memory:
        """
        Create a new memory.
        
        Args:
            persona_id: The persona this memory belongs to
            content: The memory content
            memory_type: Type of memory (fact, preference, event, relationship)
            source_message_id: ID of the message that triggered this memory
            context: Original context
            importance: Importance score (0.0 to 1.0)
        """
        memory = Memory(
            persona_id=persona_id,
            content=content,
            memory_type=memory_type,
            source_message_id=source_message_id,
            context=context,
            importance_score=importance,
            created_at=datetime.utcnow()
        )
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory
    
    def get_memories(
        self,
        persona_id: int,
        memory_type: str = None,
        limit: int = 50
    ) -> List[Memory]:
        """Get memories for a persona."""
        query = self.db.query(Memory).filter(Memory.persona_id == persona_id)
        
        if memory_type:
            query = query.filter(Memory.memory_type == memory_type)
        
        return query.order_by(desc(Memory.importance_score)).limit(limit).all()
    
    def get_relevant_memories(
        self,
        persona_id: int,
        query_text: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get memories relevant to the current query.
        
        Uses simple keyword matching. For production, consider
        using vector similarity search.
        """
        memories = self.get_memories(persona_id, limit=100)
        
        # Extract keywords from query
        keywords = self._extract_keywords(query_text)
        
        # Score memories based on keyword matches
        scored_memories = []
        for memory in memories:
            score = 0
            memory_text = f"{memory.content} {memory.context or ''}"
            
            for keyword in keywords:
                if keyword in memory_text:
                    score += 1
            
            # Boost by importance and recency
            score += memory.importance_score * 0.5
            
            if memory.last_accessed:
                days_since = (datetime.utcnow() - memory.last_accessed).days
                if days_since < 7:
                    score += 0.3
            
            if score > 0:
                scored_memories.append({
                    'memory': memory,
                    'score': score
                })
        
        # Sort by score and return top results
        scored_memories.sort(key=lambda x: x['score'], reverse=True)
        
        # Update access count for retrieved memories
        relevant_memories = []
        for item in scored_memories[:limit]:
            memory = item['memory']
            memory.access_count += 1
            memory.last_accessed = datetime.utcnow()
            relevant_memories.append({
                'id': memory.id,
                'content': memory.content,
                'type': memory.memory_type,
                'importance': memory.importance_score,
                'score': item['score']
            })
        
        self.db.commit()
        return relevant_memories
    
    def extract_memories_from_message(
        self,
        persona_id: int,
        user_message: str,
        assistant_response: str,
        session_id: int = None
    ) -> List[Memory]:
        """
        Automatically extract memories from a conversation.
        
        This analyzes the conversation to identify important
        information worth remembering.
        """
        extracted_memories = []
        
        # Pattern 1: User mentions preferences
        # 修复：使标点符号可选，支持更多表达方式
        preference_patterns = [
            (r'我喜欢(.+?)(?:[，。！]|$)', '喜欢'),
            (r'我爱(.+?)(?:[，。！]|$)', '喜欢'),
            (r'我不喜欢(.+?)(?:[，。！]|$)', '不喜欢'),
            (r'我讨厌(.+?)(?:[，。！]|$)', '不喜欢'),
            (r'我(.+?)的时候最开心', '喜欢'),
            (r'我觉得(.+?)很好', '喜欢'),
            (r'我最爱(.+?)(?:[，。！]|$)', '喜欢'),
            (r'我想要(.+?)(?:[，。！]|$)', '想要'),
        ]
        
        for pattern, preference_type in preference_patterns:
            matches = re.findall(pattern, user_message)
            for match in matches:
                # 如果 match 是元组（多捕获组），取第一个非空值
                if isinstance(match, tuple):
                    match = next((m for m in match if m), '')
                if match:  # 确保匹配内容不为空
                    content = f"用户{preference_type}{match}"
                    memory = self.create_memory(
                        persona_id=persona_id,
                        content=content,
                        memory_type=self.TYPE_PREFERENCE,
                        importance=0.8
                    )
                    extracted_memories.append(memory)
        
        # Pattern 2: User mentions facts about themselves
        # 修复：使标点符号可选
        fact_patterns = [
            r'我是(.+?)(?:[，。！]|$)',
            r'我在(.+?)工作',
            r'我住在(.+?)(?:[，。！]|$)',
            r'我今年(.+?)岁',
            r'我的(.+?)是(.+?)(?:[，。！]|$)',
            r'我是一名(.+?)(?:[，。！]|$)',
            r'我在(.+?)上学',
            r'我在(.+?)读书',
        ]
        
        for pattern in fact_patterns:
            match = re.search(pattern, user_message)
            if match:
                content = match.group(0).rstrip('，。！')
                memory = self.create_memory(
                    persona_id=persona_id,
                    content=content,
                    memory_type=self.TYPE_FACT,
                    importance=0.9
                )
                extracted_memories.append(memory)
        
        # Pattern 3: Important events
        # 修复：使标点符号可选，支持更多时间表达
        event_patterns = [
            (r'我明天(.+?)(?:[，。！]|$)', '明天'),
            (r'我后天(.+?)(?:[，。！]|$)', '后天'),
            (r'我下周(.+?)(?:[，。！]|$)', '下周'),
            (r'我昨天(.+?)(?:[，。！]|$)', '昨天'),
            (r'我今晚(.+?)(?:[，。！]|$)', '今晚'),
            (r'我等会(.+?)(?:[，。！]|$)', '等会'),
            (r'我待会(.+?)(?:[，。！]|$)', '待会'),
            (r'我周末(.+?)(?:[，。！]|$)', '周末'),
        ]
        
        for pattern, time_desc in event_patterns:
            matches = re.findall(pattern, user_message)
            for match in matches:
                if isinstance(match, tuple):
                    match = next((m for m in match if m), '')
                if match:
                    content = f"用户{time_desc}要{match}"
                    memory = self.create_memory(
                        persona_id=persona_id,
                        content=content,
                        memory_type=self.TYPE_EVENT,
                        importance=0.7
                    )
                    extracted_memories.append(memory)
        
        # Pattern 4: Topics of interest
        topics = self._extract_topics(user_message)
        for topic in topics[:3]:  # Limit to top 3 topics
            # Check if we already have this topic
            existing = self.db.query(Memory).filter(
                Memory.persona_id == persona_id,
                Memory.memory_type == self.TYPE_TOPIC,
                Memory.content.like(f"%{topic}%")
            ).first()
            
            if not existing:
                memory = self.create_memory(
                    persona_id=persona_id,
                    content=f"用户对{topic}感兴趣",
                    memory_type=self.TYPE_TOPIC,
                    importance=0.6
                )
                extracted_memories.append(memory)
        
        return extracted_memories
    
    def get_memory_context_for_chat(
        self,
        persona_id: int,
        user_message: str,
        max_memories: int = 3
    ) -> str:
        """
        Get formatted memory context to include in chat.
        
        Returns a string that can be added to the system prompt
        or user context.
        """
        relevant_memories = self.get_relevant_memories(
            persona_id, user_message, limit=max_memories
        )
        
        if not relevant_memories:
            return ""
        
        context_parts = ["\n关于用户的相关记忆："]
        for memory in relevant_memories:
            context_parts.append(f"- {memory['content']}")
        
        return "\n".join(context_parts)
    
    def update_memory_importance(self, memory_id: int, delta: float = 0.1):
        """Update the importance score of a memory."""
        memory = self.db.query(Memory).filter(Memory.id == memory_id).first()
        if memory:
            memory.importance_score = min(1.0, memory.importance_score + delta)
            self.db.commit()
    
    def consolidate_memories(self, persona_id: int):
        """
        Consolidate and clean up memories.
        
        - Remove expired memories
        - Merge similar memories
        - Update importance based on access patterns
        """
        memories = self.get_memories(persona_id, limit=200)
        
        # Remove expired memories
        for memory in memories:
            if memory.expires_at and memory.expires_at < datetime.utcnow():
                self.db.delete(memory)
        
        # Decay importance of rarely accessed memories
        for memory in memories:
            if memory.last_accessed:
                days_since = (datetime.utcnow() - memory.last_accessed).days
                if days_since > 30:
                    memory.importance_score *= 0.9  # Decay
        
        self.db.commit()
    
    def get_memory_stats(self, persona_id: int) -> Dict:
        """Get statistics about memories."""
        memories = self.get_memories(persona_id)
        
        type_counts = Counter(m.memory_type for m in memories)
        
        return {
            'total_memories': len(memories),
            'type_distribution': dict(type_counts),
            'avg_importance': sum(m.importance_score for m in memories) / len(memories) if memories else 0,
            'recently_accessed': len([m for m in memories if m.last_accessed and 
                                     (datetime.utcnow() - m.last_accessed).days < 7])
        }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        stop_words = {'的', '了', '是', '我', '你', '在', '有', '个', '吗', '吧', '呢', '啊', '和', '就', '都', '要'}
        words = []
        
        # Extract 2-grams
        for i in range(len(text) - 1):
            bigram = text[i:i+2]
            if bigram not in stop_words:
                words.append(bigram)
        
        return list(set(words))[:15]
    
    def _extract_topics(self, text: str) -> List[str]:
        """Extract potential topics from text."""
        # Common topic indicators
        topic_indicators = [
            r'关于(.+?)[，。！]',
            r'(.+?)怎么样',
            r'(.+?)好吗',
            r'(.+?)呢',
        ]
        
        topics = []
        for pattern in topic_indicators:
            matches = re.findall(pattern, text)
            topics.extend(matches)
        
        # Also look for nouns (simplified - in production use NLP)
        # For now, extract capitalized or quoted terms
        quoted = re.findall(r'["\'](.+?)["\']', text)
        topics.extend(quoted)
        
        return list(set(topics))


class ConversationMemory:
    """Manages short-term conversation context."""
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.messages: List[Dict] = []
    
    def add_message(self, role: str, content: str, emoji_url: str = None):
        """Add a message to the conversation history."""
        self.messages.append({
            'role': role,
            'content': content,
            'emoji_url': emoji_url,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Keep only recent messages
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
    
    def get_context(self, num_messages: int = None) -> List[Dict]:
        """Get recent conversation context."""
        if num_messages is None:
            return self.messages
        return self.messages[-num_messages:]
    
    def get_formatted_context(self, num_messages: int = 5) -> str:
        """Get formatted conversation history for prompt."""
        recent = self.get_context(num_messages)
        parts = []
        
        for msg in recent:
            role_name = "用户" if msg['role'] == 'user' else "助手"
            parts.append(f"{role_name}：{msg['content']}")
        
        return "\n".join(parts)
    
    def clear(self):
        """Clear conversation history."""
        self.messages = []


# Singleton instance
_memory_service = None


def get_memory_service(db: Session = None) -> MemoryService:
    """Get or create memory service singleton."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService(db)
    return _memory_service


if __name__ == "__main__":
    # Test the service
    from database import init_database
    
    init_database()
    
    service = get_memory_service()
    
    # Test memory extraction
    test_messages = [
        "我喜欢吃川菜，特别是麻辣火锅",
        "我明天要去参加一个重要的会议",
        "我觉得这部电影很好看",
    ]
    
    for msg in test_messages:
        memories = service.extract_memories_from_message(1, msg, "")
        print(f"\nMessage: {msg}")
        print(f"Extracted {len(memories)} memories")
        for m in memories:
            print(f"  - [{m.memory_type}] {m.content}")
