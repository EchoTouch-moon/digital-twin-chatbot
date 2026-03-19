"""
User Profile and Memory Summary Service for Digital Twin Chatbot.

This service manages:
1. User profile generation and updates
2. Memory summarization
3. Dynamic user modeling based on conversation history
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from database import get_db, Memory, UserProfile, MemorySummary, Persona


class UserProfileService:
    """
    用户画像服务
    
    负责：
    1. 基于对话历史生成用户画像
    2. 定期更新用户画像
    3. 生成记忆摘要
    """
    
    def __init__(self, db: Session = None, llm_service=None):
        self.db = db or get_db()
        self.llm_service = llm_service
    
    def get_or_create_user_profile(self, persona_id: int) -> UserProfile:
        """获取或创建用户画像"""
        profile = self.db.query(UserProfile).filter(
            UserProfile.persona_id == persona_id
        ).first()
        
        if not profile:
            profile = UserProfile(
                persona_id=persona_id,
                personality_traits=json.dumps({}),
                interests=json.dumps([]),
                communication_style="",
                background_summary="",
                conversation_count=0,
                relationship_stage="acquaintance",
                trust_level=0.5
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        
        return profile
    
    def generate_user_profile(self, persona_id: int, force_update: bool = False) -> UserProfile:
        """
        基于记忆生成用户画像
        
        Args:
            persona_id: 角色ID
            force_update: 是否强制更新
        """
        profile = self.get_or_create_user_profile(persona_id)
        
        # 获取该角色的所有记忆
        memories = self.db.query(Memory).filter(
            Memory.persona_id == persona_id
        ).order_by(Memory.created_at.desc()).all()
        
        if not memories:
            return profile
        
        # 如果记忆数量不足且不强制更新，跳过
        if len(memories) < 3 and not force_update:
            return profile
        
        # 分类记忆
        preferences = [m for m in memories if m.memory_type == "preference"]
        facts = [m for m in memories if m.memory_type == "fact"]
        events = [m for m in memories if m.memory_type == "event"]
        
        # 提取兴趣爱好（从偏好）
        interests = []
        for pref in preferences[:10]:  # 取最近10个偏好
            content = pref.content
            if "喜欢" in content:
                interest = content.split("喜欢")[-1].strip()
                if interest and interest not in interests:
                    interests.append(interest)
        
        # 提取背景信息（从事实）
        background_facts = []
        for fact in facts[:5]:
            background_facts.append(fact.content)
        
        # 生成沟通风格（基于记忆类型分布）
        total = len(memories)
        style_parts = []
        if len(preferences) / total > 0.3:
            style_parts.append("喜欢分享个人喜好")
        if len(events) / total > 0.3:
            style_parts.append("经常谈论计划和活动")
        if len(facts) / total > 0.3:
            style_parts.append("倾向于分享个人信息")
        
        communication_style = "，".join(style_parts) if style_parts else "沟通风格较为均衡"
        
        # 更新画像
        profile.interests = json.dumps(interests[:10], ensure_ascii=False)  # 最多10个兴趣
        profile.background_summary = "\n".join(background_facts[:5]) if background_facts else ""
        profile.communication_style = communication_style
        profile.conversation_count = len(memories)
        profile.updated_at = datetime.utcnow()
        
        # 更新关系阶段和信任度
        self._update_relationship_stage(profile, len(memories))
        
        self.db.commit()
        self.db.refresh(profile)
        
        return profile
    
    def _update_relationship_stage(self, profile: UserProfile, memory_count: int):
        """根据互动次数更新关系阶段"""
        if memory_count < 5:
            profile.relationship_stage = "acquaintance"  # 初识
            profile.trust_level = min(0.3 + memory_count * 0.05, 0.5)
        elif memory_count < 20:
            profile.relationship_stage = "friend"  # 朋友
            profile.trust_level = min(0.5 + (memory_count - 5) * 0.02, 0.7)
        elif memory_count < 50:
            profile.relationship_stage = "close_friend"  # 好友
            profile.trust_level = min(0.7 + (memory_count - 20) * 0.01, 0.9)
        else:
            profile.relationship_stage = "best_friend"  # 挚友
            profile.trust_level = 0.95
    
    def generate_memory_summary(self, persona_id: int, summary_type: str = "preference") -> Optional[MemorySummary]:
        """
        生成记忆摘要
        
        Args:
            persona_id: 角色ID
            summary_type: 摘要类型 (preference, fact, event)
        """
        # 获取指定类型的记忆
        memories = self.db.query(Memory).filter(
            Memory.persona_id == persona_id,
            Memory.memory_type == summary_type
        ).order_by(Memory.created_at.desc()).limit(20).all()
        
        if len(memories) < 3:
            return None  # 记忆不足，不生成摘要
        
        # 提取关键信息
        key_points = []
        for m in memories[:10]:
            key_points.append(m.content)
        
        # 生成摘要标题和内容
        if summary_type == "preference":
            title = f"用户偏好摘要 ({len(memories)}条记忆)"
            content = "用户的主要偏好包括：\n" + "\n".join([f"- {p}" for p in key_points[:5]])
        elif summary_type == "fact":
            title = f"用户背景摘要 ({len(memories)}条记忆)"
            content = "用户的重要信息：\n" + "\n".join([f"- {f}" for f in key_points[:5]])
        elif summary_type == "event":
            title = f"近期活动摘要 ({len(memories)}条记忆)"
            content = "用户的近期活动：\n" + "\n".join([f"- {e}" for e in key_points[:5]])
        else:
            title = f"记忆摘要 ({len(memories)}条记忆)"
            content = "\n".join([f"- {p}" for p in key_points[:5]])
        
        # 创建摘要
        summary = MemorySummary(
            persona_id=persona_id,
            summary_type=summary_type,
            title=title,
            content=content,
            key_points=json.dumps(key_points, ensure_ascii=False),
            source_memory_ids=json.dumps([m.id for m in memories]),
            memory_count=len(memories),
            start_date=memories[-1].created_at,  # 最早的记忆
            end_date=memories[0].created_at,  # 最近的记忆
            importance_score=0.7
        )
        
        self.db.add(summary)
        self.db.commit()
        self.db.refresh(summary)
        
        return summary
    
    def get_user_profile_for_prompt(self, persona_id: int) -> str:
        """
        获取格式化的用户画像，用于系统提示词
        
        Returns:
            格式化的用户画像字符串
        """
        profile = self.get_or_create_user_profile(persona_id)
        
        if not profile:
            return ""
        
        parts = []
        
        # 关系阶段
        stage_names = {
            "acquaintance": "初识阶段",
            "friend": "朋友阶段",
            "close_friend": "好友阶段",
            "best_friend": "挚友阶段"
        }
        parts.append(f"关系阶段：{stage_names.get(profile.relationship_stage, profile.relationship_stage)}")
        
        # 兴趣爱好
        try:
            interests = json.loads(profile.interests) if profile.interests else []
            if interests:
                parts.append(f"兴趣爱好：{', '.join(interests[:5])}")
        except:
            pass
        
        # 沟通风格
        if profile.communication_style:
            parts.append(f"沟通特点：{profile.communication_style}")
        
        # 背景摘要
        if profile.background_summary:
            parts.append(f"背景信息：{profile.background_summary[:200]}")
        
        return "\n".join(parts) if parts else ""
    
    def get_memory_summaries_for_prompt(self, persona_id: int) -> str:
        """
        获取记忆摘要，用于系统提示词
        """
        summaries = self.db.query(MemorySummary).filter(
            MemorySummary.persona_id == persona_id
        ).order_by(MemorySummary.created_at.desc()).limit(3).all()
        
        if not summaries:
            return ""
        
        parts = ["\n重要记忆摘要："]
        for summary in summaries:
            parts.append(f"\n【{summary.title}】")
            parts.append(summary.content[:300])  # 限制长度
        
        return "\n".join(parts)
    
    def should_update_profile(self, persona_id: int, min_conversations: int = 5) -> bool:
        """
        判断是否需要更新用户画像
        
        当新增记忆数量达到阈值时触发更新
        """
        profile = self.get_or_create_user_profile(persona_id)
        
        # 获取当前记忆数量
        current_count = self.db.query(Memory).filter(
            Memory.persona_id == persona_id
        ).count()
        
        # 如果记忆数量增加了一定数量，触发更新
        return (current_count - profile.conversation_count) >= min_conversations
    
    def auto_update_if_needed(self, persona_id: int) -> bool:
        """
        自动更新用户画像和记忆摘要（如果需要）
        
        Returns:
            是否执行了更新
        """
        if not self.should_update_profile(persona_id):
            return False
        
        # 更新用户画像
        self.generate_user_profile(persona_id)
        
        # 生成各类记忆摘要
        for summary_type in ["preference", "fact", "event"]:
            self.generate_memory_summary(persona_id, summary_type)
        
        return True


# Singleton instance
_profile_service = None


def get_user_profile_service(llm_service=None) -> UserProfileService:
    """获取用户画像服务单例"""
    global _profile_service
    if _profile_service is None:
        _profile_service = UserProfileService(llm_service=llm_service)
    return _profile_service
