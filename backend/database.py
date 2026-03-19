"""
Database models and configuration for the Digital Twin Chatbot.

This module defines SQLAlchemy models for:
- Users (personas)
- Chat sessions
- Messages
- Memories
- Chat history for RAG
"""

import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

# Database file path
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chatbot.db")

# Create engine
engine = create_engine(f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Persona(Base):
    """Represents a digital twin persona (a person to mimic)."""
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    avatar_url = Column(String(500))

    # Personality traits extracted from chat history
    personality_traits = Column(JSON, default=dict)  # {"formality": 0.7, "humor": 0.8, ...}
    common_phrases = Column(JSON, default=list)  # ["口头禅1", "口头禅2"]
    emoji_preferences = Column(JSON, default=list)  # Preferred emoji categories

    # Emoji behavior analysis - 新增字段
    emoji_usage_frequency = Column(String(20), default="medium")  # "high", "medium", "low", "none"
    emoji_usage_rate = Column(Float, default=0.5)  # 0.0-1.0 表情包使用率
    emoji_scenario_prefs = Column(JSON, default=list)  # ["开心", "难过", "调侃"] 常用场景
    emoji_type_prefs = Column(JSON, default=list)  # ["搞笑", "可爱", "表情动作"] 类型偏好

    # Chat style characteristics
    avg_response_length = Column(Integer, default=50)  # Average characters per response
    response_style = Column(String(50), default="casual")  # formal, casual, humorous, etc.

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chat_sessions = relationship("ChatSession", back_populates="persona")
    memories = relationship("Memory", back_populates="persona")
    chat_history = relationship("ChatHistory", back_populates="persona")
    user_profile = relationship("UserProfile", back_populates="persona", uselist=False)
    memory_summaries = relationship("MemorySummary", back_populates="persona")


class ChatSession(Base):
    """Represents a chat session between a user and a persona."""
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), index=True)  # Could be anonymous or authenticated
    persona_id = Column(Integer, ForeignKey("personas.id"))
    title = Column(String(200))  # Auto-generated or user-defined
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    persona = relationship("Persona", back_populates="chat_sessions")
    messages = relationship("Message", back_populates="session", order_by="Message.created_at")


class Message(Base):
    """Represents a single message in a chat session."""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"))
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    
    # Optional: associated emoji
    emoji_url = Column(String(500))
    emoji_description = Column(String(500))
    
    # Metadata
    sentiment = Column(String(20))  # happy, sad, angry, neutral, etc.
    topics = Column(JSON, default=list)  # Extracted topics
    
    # User feedback
    user_feedback = Column(Integer)  # 1: thumbs up, -1: thumbs down, None: no feedback
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")


class Memory(Base):
    """Represents a long-term memory about the user or conversation."""
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"))
    
    # Memory content
    content = Column(Text, nullable=False)
    memory_type = Column(String(50), default="fact")  # fact, preference, event, relationship
    
    # Context
    source_message_id = Column(Integer, ForeignKey("messages.id"))
    context = Column(Text)  # Original context where this was extracted
    
    # Importance and decay
    importance_score = Column(Float, default=1.0)  # 0.0 to 1.0
    access_count = Column(Integer, default=0)  # How many times this was retrieved
    last_accessed = Column(DateTime)
    
    # Temporal info
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  # Optional expiration
    
    # Relationships
    persona = relationship("Persona", back_populates="memories")


class ChatHistory(Base):
    """
    Stores historical chat pairs for RAG retrieval.
    This is used to find similar past conversations.
    """
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"))
    
    # The conversation pair
    user_message = Column(Text, nullable=False)
    assistant_response = Column(Text, nullable=False)
    
    # Context
    conversation_context = Column(Text)  # Previous messages for context
    
    # Metadata for retrieval
    user_message_embedding = Column(JSON)  # Vector embedding (stored as JSON for SQLite)
    topics = Column(JSON, default=list)
    sentiment = Column(String(20))
    
    # Source info
    source_file = Column(String(500))  # Original chat export file
    imported_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    persona = relationship("Persona", back_populates="chat_history")


class EmojiFeedback(Base):
    """Stores user feedback on emoji recommendations for learning."""
    __tablename__ = "emoji_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    
    emoji_file = Column(String(200), nullable=False)
    was_appropriate = Column(Boolean)  # True if user liked it, False otherwise
    
    context_sentiment = Column(String(20))
    user_reaction = Column(String(50))  # What emoji the user actually used (if any)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    """
    用户画像 - 动态维护的用户特征描述
    
    基于对话历史自动生成的用户特征摘要，包括：
    - 性格特征
    - 兴趣爱好
    - 聊天风格偏好
    - 重要背景信息
    """
    __tablename__ = "user_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), unique=True)
    
    # 用户画像内容
    personality_traits = Column(Text)  # 性格特征（JSON格式）
    interests = Column(Text)  # 兴趣爱好（JSON格式）
    communication_style = Column(Text)  # 沟通风格描述
    background_summary = Column(Text)  # 背景摘要
    
    # 画像生成信息
    generated_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    conversation_count = Column(Integer, default=0)  # 基于多少轮对话生成
    
    # 关系信息
    relationship_stage = Column(String(50), default="acquaintance")  # 关系阶段
    trust_level = Column(Float, default=0.5)  # 信任度 0-1
    
    # Relationships
    persona = relationship("Persona", back_populates="user_profile")


class MemorySummary(Base):
    """
    记忆摘要 - 定期总结的重要记忆

    将多个相关记忆聚合成高层摘要，减少检索时的噪声
    """
    __tablename__ = "memory_summaries"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"))

    # 摘要内容
    summary_type = Column(String(50))  # preference_summary, event_summary, etc.
    title = Column(String(200))  # 摘要标题
    content = Column(Text)  # 摘要内容
    key_points = Column(Text)  # 关键点（JSON格式）

    # 来源记忆
    source_memory_ids = Column(Text)  # 来源记忆ID列表（JSON）
    memory_count = Column(Integer, default=0)  # 包含多少条记忆

    # 时间范围
    start_date = Column(DateTime)  # 覆盖的记忆开始时间
    end_date = Column(DateTime)  # 覆盖的记忆结束时间

    # 元信息
    importance_score = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    persona = relationship("Persona", back_populates="memory_summaries")


class Scratchpad(Base):
    """
    临时工作区 - 当前会话状态

    存储当前会话的临时信息，会话结束后自动过期
    """
    __tablename__ = "scratchpads"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"))
    session_id = Column(Integer, ForeignKey("chat_sessions.id"))

    # 工作区内容
    current_task = Column(Text)  # 当前任务
    pending_steps = Column(JSON, default=list)  # 待完成步骤
    emotional_state = Column(String(50))  # 当前情绪
    key_context = Column(Text)  # 关键上下文
    active_topics = Column(JSON, default=list)  # 当前讨论话题

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime)  # 过期时间（会话结束后）

    # Relationships
    persona = relationship("Persona", backref="scratchpads")
    session = relationship("ChatSession", backref="scratchpad")


class TimelineJournal(Base):
    """
    时间线日记 - 每日/每周总结

    AI自动生成的对话摘要，赋予AI时间观念
    """
    __tablename__ = "timeline_journals"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"))

    # 时间信息
    journal_type = Column(String(20))  # "daily" / "weekly"
    date = Column(DateTime, index=True)  # 日记日期

    # 内容
    summary = Column(Text)  # AI生成的摘要
    key_events = Column(JSON, default=list)  # 关键事件列表
    preference_changes = Column(JSON, default=list)  # 偏好变化
    mood_trend = Column(String(50))  # 情绪趋势

    # 统计
    message_count = Column(Integer, default=0)  # 消息数量
    topics_discussed = Column(JSON, default=list)  # 讨论话题

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    persona = relationship("Persona", backref="timeline_journals")


class MemoryVersion(Base):
    """
    记忆版本追踪

    记录记忆的变更历史，支持矛盾记忆的追溯
    """
    __tablename__ = "memory_versions"

    id = Column(Integer, primary_key=True, index=True)
    memory_id = Column(Integer, ForeignKey("memories.id"))

    # 版本信息
    version = Column(Integer, default=1)
    old_content = Column(Text)  # 旧内容
    new_content = Column(Text)  # 新内容
    change_reason = Column(String(200))  # 变更原因
    conflict_resolved = Column(Boolean, default=False)  # 是否为冲突解决

    # 元数据
    changed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    memory = relationship("Memory", backref="versions")


class HotMemory(Base):
    """
    热记忆 - 高频访问的记忆直接注入System Prompt

    存储高频口头禅、核心Persona特征等，减少向量检索开销
    """
    __tablename__ = "hot_memories"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"))

    # 热记忆内容
    content = Column(Text, nullable=False)
    memory_type = Column(String(50))  # catchphrase, core_trait, recent_context
    access_frequency = Column(Integer, default=0)  # 访问频率

    # 来源
    source_memory_id = Column(Integer, ForeignKey("memories.id"), nullable=True)

    # 元数据
    last_promoted = Column(DateTime)  # 上次提升为热记忆的时间
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    persona = relationship("Persona", backref="hot_memories")


# Database utility functions
def get_db() -> Session:
    """Get a database session."""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def init_database():
    """Initialize the database, creating all tables."""
    Base.metadata.create_all(bind=engine)
    print(f"[Database] Initialized at {DATABASE_PATH}")


def get_or_create_default_persona(db: Session) -> Persona:
    """Get or create a default persona."""
    persona = db.query(Persona).filter(Persona.name == "Default Assistant").first()
    if not persona:
        persona = Persona(
            name="Default Assistant",
            description="A friendly digital twin assistant",
            personality_traits={"friendliness": 0.9, "humor": 0.6, "formality": 0.3},
            response_style="casual"
        )
        db.add(persona)
        db.commit()
        db.refresh(persona)
    return persona


# Export for use in other modules
__all__ = [
    "Base", "engine", "SessionLocal", "get_db", "init_database",
    "Persona", "ChatSession", "Message", "Memory", "ChatHistory", "EmojiFeedback",
    "UserProfile", "MemorySummary", "Scratchpad", "TimelineJournal", "MemoryVersion", "HotMemory",
    "get_or_create_default_persona"
]
