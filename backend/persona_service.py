"""
Persona Service for Digital Twin Chatbot.

This service manages persona creation, chat history import,
personality analysis, and dynamic prompt generation.
Uses ChromaDB for vector storage of conversation embeddings.
"""

import json
import os
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from sqlalchemy.orm import Session

from database import (
    get_db, Persona, ChatHistory, ChatSession, Message,
    get_or_create_default_persona
)
from chat_history_processor import ChatHistoryProcessor, ChatMessage

# Import ChromaDB service
try:
    from chroma_service import get_chroma_service, ChromaService
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("[PersonaService] Warning: ChromaDB service not available")


class PersonaService:
    """
    数字孪生角色管理服务类
    
    主要职责：
    1. 创建和管理数字孪生角色（Persona）
    2. 导入和处理聊天记录
    3. 分析角色性格特征
    4. 生成系统提示词（System Prompt）
    5. 使用 ChromaDB 存储对话嵌入向量
    
    属性：
        db: SQLAlchemy 数据库会话
        history_processor: 聊天记录处理器
        emoji_classification: 表情包分类映射表
        chroma_service: ChromaDB 向量数据库服务
    """
    
    def __init__(self, db: Session = None, use_chroma: bool = True):
        """
        初始化角色管理服务
        
        参数：
            db: 数据库会话，如果为 None 则自动创建
            use_chroma: 是否使用 ChromaDB 向量存储
        """
        # 初始化数据库会话
        self.db = db or get_db()
        
        # 初始化聊天记录处理器（临时使用空字符串，后续根据实际角色名称更新）
        # ChatHistoryProcessor 需要 target_person_name 参数来识别目标人物的消息
        self.history_processor = ChatHistoryProcessor(target_person_name="")
        
        # 加载表情包分类数据（MD5 -> 描述信息映射）
        self.emoji_classification = self._load_emoji_classification()
        
        # Initialize ChromaDB service
        self.chroma_service: Optional[ChromaService] = None
        if use_chroma and CHROMADB_AVAILABLE:
            try:
                self.chroma_service = get_chroma_service()
                print("[PersonaService] ChromaDB service initialized")
            except Exception as e:
                print(f"[PersonaService] Error initializing ChromaDB: {e}")
                print("[PersonaService] Falling back to SQLite storage")
    
    def _load_emoji_classification(self) -> Dict[str, Dict]:
        """Load emoji classification data with MD5 to description mapping."""
        emoji_map = {}
        classification_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "emoji_classification.jsonl"
        )
        
        if os.path.exists(classification_file):
            try:
                with open(classification_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            # Extract MD5 from filename (e.g., "a9aa1bdc25333fdb5d470ea03c4fc5a3.gif")
                            filename = data.get('file_name', '')
                            if filename:
                                md5 = filename.replace('.gif', '').replace('.png', '')
                                emoji_map[md5] = {
                                    'top_category': data.get('top_category', '其他'),
                                    'sub_category': data.get('sub_category', ''),
                                    'description': data.get('description', ''),
                                    'file_name': filename
                                }
                        except json.JSONDecodeError:
                            continue
                print(f"[PersonaService] Loaded {len(emoji_map)} emoji classifications")
            except Exception as e:
                print(f"[PersonaService] Error loading emoji classification: {e}")
        
        return emoji_map
    
    def create_persona(
        self,
        name: str,
        description: str = None,
        avatar_url: str = None
    ) -> Persona:
        """Create a new digital twin persona."""
        persona = Persona(
            name=name,
            description=description or f"Digital twin of {name}",
            avatar_url=avatar_url,
            personality_traits={},
            common_phrases=[],
            emoji_preferences=[],
            avg_response_length=50,
            response_style="casual"
        )
        self.db.add(persona)
        self.db.commit()
        self.db.refresh(persona)
        print(f"[PersonaService] Created persona: {name} (ID: {persona.id})")
        return persona
    
    def get_persona(self, persona_id: int) -> Optional[Persona]:
        """Get a persona by ID."""
        return self.db.query(Persona).filter(Persona.id == persona_id).first()
    
    def get_persona_by_name(self, name: str) -> Optional[Persona]:
        """Get a persona by name."""
        return self.db.query(Persona).filter(Persona.name == name).first()
    
    def list_personas(self) -> List[Persona]:
        """List all personas."""
        return self.db.query(Persona).all()
    
    def import_chat_history(
        self,
        persona_id: int,
        file_path: str,
        persona_identifier: str = None
    ) -> Dict[str, Any]:
        """
        Import chat history from a WeChat export file.
        
        Args:
            persona_id: The persona to associate this history with
            file_path: Path to the WeChat export JSON file
            persona_identifier: How the persona is identified in the chat (name/username)
        
        Returns:
            Statistics about the import
        """
        persona = self.get_persona(persona_id)
        if not persona:
            raise ValueError(f"Persona with ID {persona_id} not found")
        
        # Parse the chat history
        messages = self.history_processor.parse_wechat_export(file_path)
        
        if not messages:
            return {"status": "error", "message": "No messages found in file"}
        
        # Auto-detect persona identifier if not provided
        if not persona_identifier:
            persona_identifier = self._detect_persona_identifier(messages, persona.name)
        
        # Extract conversation pairs
        pairs = self.history_processor.extract_conversation_pairs(
            messages, persona_identifier
        )
        
        # Analyze personality
        personality = self.history_processor.analyze_personality(messages, persona_identifier)
        
        # Update persona with analyzed traits
        self._update_persona_from_analysis(persona, personality)
        
        # Store conversation pairs in both SQLite and ChromaDB
        stored_count = 0
        chroma_conversations = []
        
        for pair in pairs:
            # Look up emoji descriptions if present
            enhanced_response = self._enhance_with_emoji_info(pair['response'])
            
            # Store in SQLite (for backup and metadata)
            chat_history = ChatHistory(
                persona_id=persona_id,
                user_message=pair['user_message'],
                assistant_response=enhanced_response,
                conversation_context=json.dumps(pair['context'], ensure_ascii=False),
                topics=json.dumps(pair['topics'], ensure_ascii=False),
                sentiment=pair['sentiment'],
                source_file=file_path
            )
            self.db.add(chat_history)
            stored_count += 1
            
            # Prepare for ChromaDB batch insert
            if self.chroma_service:
                chroma_conversations.append({
                    "persona_id": persona_id,
                    "user_message": pair['user_message'],
                    "assistant_response": enhanced_response,
                    "conversation_context": json.dumps(pair['context'], ensure_ascii=False),
                    "topics": pair['topics'],
                    "sentiment": pair['sentiment'],
                    "source_file": file_path
                })
        
        self.db.commit()
        
        # Store in ChromaDB for vector search (batch insert)
        if self.chroma_service and chroma_conversations:
            try:
                self.chroma_service.add_conversations_batch(chroma_conversations)
                print(f"[PersonaService] Stored {len(chroma_conversations)} conversations in ChromaDB")
            except Exception as e:
                print(f"[PersonaService] Error storing in ChromaDB: {e}")
        
        stats = {
            "status": "success",
            "total_messages": len(messages),
            "conversation_pairs": len(pairs),
            "stored_pairs": stored_count,
            "personality_traits": personality,
            "persona_id": persona_id
        }
        
        print(f"[PersonaService] Imported {stored_count} conversation pairs for {persona.name}")
        return stats
    
    def _detect_persona_identifier(self, messages: List[ChatMessage], persona_name: str) -> str:
        """Auto-detect how the persona is identified in the chat."""
        # Count occurrences of each sender
        sender_counts = Counter()
        for msg in messages:
            if msg.sender_name:
                sender_counts[msg.sender_name] += 1
        
        # Try to match with persona name
        for sender, count in sender_counts.most_common():
            if persona_name in sender or sender in persona_name:
                return sender
        
        # Return the most frequent sender as fallback
        if sender_counts:
            return sender_counts.most_common(1)[0][0]
        
        return persona_name
    
    def _update_persona_from_analysis(self, persona: Persona, personality: Dict):
        """Update persona attributes based on personality analysis."""
        # Update personality traits
        persona.personality_traits = {
            "formality": personality.get("formality", 0.5),
            "humor": personality.get("humor", 0.5),
            "warmth": personality.get("warmth", 0.5),
            "expressiveness": personality.get("expressiveness", 0.5)
        }
        
        # Update common phrases
        persona.common_phrases = personality.get("common_phrases", [])
        
        # Update emoji preferences
        persona.emoji_preferences = personality.get("emoji_preferences", [])
        
        # Update response characteristics
        avg_length = personality.get("avg_response_length", 50)
        persona.avg_response_length = min(avg_length, 200)  # Cap at 200
        
        # Determine response style
        if personality.get("formality", 0.5) > 0.7:
            persona.response_style = "formal"
        elif personality.get("humor", 0.5) > 0.7:
            persona.response_style = "humorous"
        else:
            persona.response_style = "casual"
        
        persona.updated_at = datetime.utcnow()
        self.db.commit()
    
    def _enhance_with_emoji_info(self, message: str) -> str:
        """Enhance message with emoji description from classification."""
        # Pattern to match emoji references like [表情：a9aa1bdc...]
        pattern = r'\[表情：([a-f0-9]{32})\]'
        
        def replace_emoji(match):
            md5 = match.group(1)
            if md5 in self.emoji_classification:
                emoji_info = self.emoji_classification[md5]
                return f"[表情：{emoji_info['top_category']}-{emoji_info['sub_category']}]"
            return match.group(0)
        
        return re.sub(pattern, replace_emoji, message)
    
    def generate_system_prompt(
        self,
        persona_id: int,
        user_context: Dict = None,
        include_examples: bool = True,
        num_examples: int = 3
    ) -> str:
        """
        Generate a dynamic system prompt for the persona.
        
        Args:
            persona_id: The persona to generate prompt for
            user_context: Optional context about the user
            include_examples: Whether to include few-shot examples
            num_examples: Number of examples to include
        
        Returns:
            The generated system prompt
        """
        persona = self.get_persona(persona_id)
        if not persona:
            return self._get_default_system_prompt()
        
        # Build base prompt
        prompt_parts = []
        
        # Identity section
        prompt_parts.append(f"你是{persona.name}的数字孪生智能体。你需要模仿{persona.name}的说话风格、用词习惯和情感表达方式。")
        
        if persona.description:
            prompt_parts.append(f"简介：{persona.description}")
        
        # Personality traits
        traits = persona.personality_traits or {}
        style_descriptions = []
        
        if traits.get("formality", 0.5) > 0.7:
            style_descriptions.append("说话比较正式、礼貌")
        elif traits.get("formality", 0.5) < 0.3:
            style_descriptions.append("说话随意、亲切")
        
        if traits.get("humor", 0.5) > 0.6:
            style_descriptions.append("喜欢开玩笑，比较幽默")
        
        if traits.get("warmth", 0.5) > 0.6:
            style_descriptions.append("语气温暖、关心他人")
        
        if traits.get("expressiveness", 0.5) > 0.6:
            style_descriptions.append("表达丰富，情感外露")
        
        if style_descriptions:
            prompt_parts.append("性格特点：" + "。".join(style_descriptions) + "。")
        
        # Common phrases
        phrases = persona.common_phrases or []
        if phrases:
            prompt_parts.append(f"常用口头禅：{', '.join(phrases[:5])}")
        
        # Response style guidelines
        prompt_parts.append(f"\n回复风格要求：")
        prompt_parts.append(f"- 回复长度控制在{persona.avg_response_length or 50}字左右")
        prompt_parts.append(f"- 使用{self._get_style_description(persona.response_style)}的语气")
        prompt_parts.append(f"- 保持自然的对话节奏，像日常聊天一样")
        prompt_parts.append(f"- 不要使用书面语或过于正式的表达")
        
        # Emoji usage guidelines
        emoji_prefs = persona.emoji_preferences or []
        if emoji_prefs:
            top_categories = [cat for cat, _ in Counter(emoji_prefs).most_common(3)]
            prompt_parts.append(f"\n表情使用偏好：")
            prompt_parts.append(f"- 喜欢使用以下类型的表情：{', '.join(top_categories)}")
            prompt_parts.append(f"- 根据对话情境选择合适的表情")
            prompt_parts.append(f"- 表情要自然，不要过度使用")
        
        # Important: No Unicode emojis
        prompt_parts.append(f"\n重要提示：")
        prompt_parts.append(f"- 不要在回复中包含emoji字符（如😊、😂等）")
        prompt_parts.append(f"- 系统会根据你的回复自动推荐合适的表情包")
        prompt_parts.append(f"- 专注于文字内容的自然表达")
        
        # Include few-shot examples if requested
        if include_examples:
            examples = self._get_few_shot_examples(persona_id, num_examples)
            if examples:
                prompt_parts.append(f"\n参考对话示例（学习以下说话风格）：")
                for i, example in enumerate(examples, 1):
                    prompt_parts.append(f"\n示例{i}：")
                    prompt_parts.append(f"对方：{example['user_message']}")
                    prompt_parts.append(f"你：{example['assistant_response']}")
        
        # User context
        if user_context:
            prompt_parts.append(f"\n当前对话对象信息：")
            if 'name' in user_context:
                prompt_parts.append(f"- 对方姓名：{user_context['name']}")
            if 'relationship' in user_context:
                prompt_parts.append(f"- 关系：{user_context['relationship']}")
            if 'known_facts' in user_context:
                prompt_parts.append(f"- 已知信息：{user_context['known_facts']}")
        
        return "\n".join(prompt_parts)
    
    def _get_style_description(self, style: str) -> str:
        """Get human-readable description of response style."""
        style_map = {
            "formal": "正式",
            "casual": "随意自然",
            "humorous": "幽默风趣",
            "warm": "温暖亲切",
            "professional": "专业"
        }
        return style_map.get(style, "自然")
    
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt when no persona is found."""
        return """你是一个友好的AI助手。请用自然、亲切的方式回复用户。

重要提示：
- 不要在回复中包含emoji字符（如😊、😂等）
- 系统会根据你的回复自动推荐合适的表情包
- 保持回复简洁自然"""
    
    def _get_few_shot_examples(self, persona_id: int, num_examples: int) -> List[Dict]:
        """Get few-shot examples from chat history using ChromaDB or SQLite fallback."""
        # Try ChromaDB first for better semantic search
        if self.chroma_service:
            try:
                # Get random sample from ChromaDB (we don't have a specific query here)
                # So we fall back to getting recent conversations
                conversations = self.chroma_service.get_conversations_by_persona(
                    persona_id=persona_id,
                    limit=num_examples * 10
                )
                
                # Filter for quality examples
                quality_examples = []
                for doc in conversations:
                    user_len = len(doc.user_message)
                    resp_len = len(doc.assistant_response)
                    if 5 <= user_len <= 100 and 10 <= resp_len <= 150:
                        quality_examples.append({
                            'user_message': doc.user_message,
                            'assistant_response': doc.assistant_response
                        })
                    if len(quality_examples) >= num_examples:
                        break
                
                if quality_examples:
                    return quality_examples
                    
            except Exception as e:
                print(f"[PersonaService] Error getting examples from ChromaDB: {e}")
        
        # Fallback to SQLite
        examples = self.db.query(ChatHistory).filter(
            ChatHistory.persona_id == persona_id
        ).order_by(
            ChatHistory.imported_at.desc()
        ).limit(num_examples * 10).all()
        
        # Filter for quality examples
        quality_examples = []
        for ex in examples:
            user_len = len(ex.user_message)
            resp_len = len(ex.assistant_response)
            if 5 <= user_len <= 100 and 10 <= resp_len <= 150:
                quality_examples.append({
                    'user_message': ex.user_message,
                    'assistant_response': ex.assistant_response
                })
            if len(quality_examples) >= num_examples:
                break
        
        return quality_examples
    
    def get_similar_conversations(
        self,
        persona_id: int,
        query: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get similar past conversations for context using ChromaDB vector search.
        Falls back to keyword-based search if ChromaDB is not available.
        """
        # Try ChromaDB vector search first
        if self.chroma_service:
            try:
                results = self.chroma_service.search_similar_conversations(
                    query=query,
                    persona_id=persona_id,
                    top_k=limit,
                    score_threshold=0.2
                )
                
                if results:
                    return results
                    
            except Exception as e:
                print(f"[PersonaService] Error searching ChromaDB: {e}")
        
        # Fallback to keyword-based search
        print("[PersonaService] Using fallback keyword search")
        keywords = self._extract_keywords(query)
        
        # Search in chat history
        results = []
        history = self.db.query(ChatHistory).filter(
            ChatHistory.persona_id == persona_id
        ).all()
        
        for entry in history:
            score = 0
            entry_text = f"{entry.user_message} {entry.assistant_response}"
            
            for keyword in keywords:
                if keyword in entry_text:
                    score += 1
            
            if score > 0:
                results.append({
                    'score': score,
                    'user_message': entry.user_message,
                    'assistant_response': entry.assistant_response,
                    'topics': json.loads(entry.topics) if entry.topics else []
                })
        
        # Sort by score and return top results
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for matching."""
        # Simple keyword extraction - in production, use NLP
        # Remove common stop words
        stop_words = {'的', '了', '是', '我', '你', '在', '有', '个', '吗', '吧', '呢', '啊'}
        words = []
        for word in text:
            if len(word) >= 2 and word not in stop_words:
                words.append(word)
        
        # Also include 2-grams
        for i in range(len(text) - 1):
            bigram = text[i:i+2]
            if bigram not in stop_words:
                words.append(bigram)
        
        return list(set(words))[:10]  # Limit keywords
    
    def update_persona_from_feedback(
        self,
        persona_id: int,
        feedback_data: Dict
    ):
        """Update persona based on user feedback."""
        persona = self.get_persona(persona_id)
        if not persona:
            return
        
        # Update based on feedback type
        if feedback_data.get('type') == 'emoji_preference':
            # Track emoji preferences
            current_prefs = persona.emoji_preferences or []
            new_category = feedback_data.get('category')
            if new_category and new_category not in current_prefs:
                current_prefs.append(new_category)
                persona.emoji_preferences = current_prefs[-10:]  # Keep last 10
        
        elif feedback_data.get('type') == 'style_adjustment':
            # Adjust style based on feedback
            traits = persona.personality_traits or {}
            if 'formality' in feedback_data:
                traits['formality'] = feedback_data['formality']
            if 'humor' in feedback_data:
                traits['humor'] = feedback_data['humor']
            persona.personality_traits = traits
        
        self.db.commit()


# Singleton instance
_persona_service = None


def get_persona_service(db: Session = None) -> PersonaService:
    """Get or create persona service singleton."""
    global _persona_service
    if _persona_service is None:
        _persona_service = PersonaService(db)
    return _persona_service


if __name__ == "__main__":
    # Test the service
    from database import init_database
    
    init_database()
    
    service = get_persona_service()
    
    # Create a test persona
    persona = service.create_persona(
        name="示例人物",
        description="一个活泼可爱的数字孪生智能体"
    )
    
    # Generate system prompt
    prompt = service.generate_system_prompt(persona.id)
    print("\n" + "="*50)
    print("Generated System Prompt:")
    print("="*50)
    print(prompt)
