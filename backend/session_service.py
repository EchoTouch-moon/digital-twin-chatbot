"""
Session Service for Digital Twin Chatbot.

管理会话和消息的持久化存储。

核心功能：
1. 每个 Persona 自动创建一个默认 Session
2. 保存用户和助手消息到数据库
3. 查询历史消息用于前端加载
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from database import get_db, ChatSession, Message


class SessionService:
    """会话管理服务 - 处理对话持久化"""

    def __init__(self, db: Session = None):
        self.db = db or get_db()

    def get_or_create_session(
        self,
        persona_id: int,
        user_id: str = "default"
    ) -> ChatSession:
        """
        获取或创建 Persona 的默认会话

        设计理念：每个 Persona 有且仅有一个默认会话
        这样可以简化前端逻辑，无需管理多会话

        Args:
            persona_id: Persona ID
            user_id: 用户标识，默认为 "default"（单用户系统）

        Returns:
            ChatSession: 该 Persona 的默认会话
        """
        # 查找已存在的默认会话
        session = self.db.query(ChatSession).filter(
            ChatSession.persona_id == persona_id,
            ChatSession.user_id == user_id
        ).first()

        if session:
            return session

        # 创建新会话
        session = ChatSession(
            user_id=user_id,
            persona_id=persona_id,
            title=f"与 Persona {persona_id} 的对话"
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        print(f"[SessionService] Created new session {session.id} for persona {persona_id}")
        return session

    def add_message(
        self,
        session_id: int,
        role: str,
        content: str,
        emoji_url: str = None,
        emoji_description: str = None
    ) -> Message:
        """
        添加消息到会话

        Args:
            session_id: 会话 ID
            role: 消息角色 ("user" 或 "assistant")
            content: 消息内容
            emoji_url: 表情包 URL（可选）
            emoji_description: 表情包描述（可选）

        Returns:
            Message: 创建的消息对象
        """
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            emoji_url=emoji_url,
            emoji_description=emoji_description
        )
        self.db.add(message)

        # 更新会话的 updated_at 时间戳
        session = self.db.query(ChatSession).filter(
            ChatSession.id == session_id
        ).first()
        if session:
            session.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(message)
        return message

    def get_session_messages(
        self,
        session_id: int,
        limit: int = 100
    ) -> List[Message]:
        """
        获取会话的所有消息

        Args:
            session_id: 会话 ID
            limit: 最大返回数量，默认 100

        Returns:
            List[Message]: 消息列表，按时间升序排列
        """
        return self.db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(
            Message.created_at.asc()
        ).limit(limit).all()

    def get_persona_messages(
        self,
        persona_id: int,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取 Persona 所有消息（用于前端加载）

        Args:
            persona_id: Persona ID
            limit: 最大返回数量

        Returns:
            List[Dict]: 格式化的消息列表
        """
        session = self.get_or_create_session(persona_id)
        messages = self.get_session_messages(session.id, limit)

        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "imageUrl": msg.emoji_url,
                "emojiInfo": {
                    "description": msg.emoji_description
                } if msg.emoji_description else None,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in messages
        ]

    def get_session_id(self, persona_id: int) -> Optional[int]:
        """
        获取 Persona 的 session_id

        Args:
            persona_id: Persona ID

        Returns:
            Optional[int]: session_id，如果不存在返回 None
        """
        session = self.db.query(ChatSession).filter(
            ChatSession.persona_id == persona_id
        ).first()
        return session.id if session else None


# 全局单例
_session_service = None


def get_session_service(db: Session = None) -> SessionService:
    """
    获取 SessionService 单例

    Args:
        db: 可选的数据库会话

    Returns:
        SessionService: 会话服务实例
    """
    global _session_service
    if _session_service is None:
        _session_service = SessionService(db)
    return _session_service