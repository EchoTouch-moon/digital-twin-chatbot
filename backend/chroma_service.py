"""
ChromaDB Service for Digital Twin Chatbot.

This service provides vector storage and retrieval for conversation embeddings
using ChromaDB, replacing the SQLite-based ChatHistory storage for better
semantic search capabilities.
"""

import json
import os
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict

# Try to import ChromaDB
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("[ChromaDB] Warning: chromadb not available, install with: pip install chromadb")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("[ChromaDB] Warning: sentence-transformers not available")


@dataclass
class ConversationDocument:
    """Represents a conversation pair document for vector storage."""
    id: str
    persona_id: int
    user_message: str
    assistant_response: str
    conversation_context: str
    topics: List[str]
    sentiment: str
    source_file: str
    created_at: str
    
    def to_metadata(self) -> Dict[str, Any]:
        """Convert to ChromaDB metadata format."""
        return {
            "persona_id": self.persona_id,
            "user_message": self.user_message,
            "assistant_response": self.assistant_response,
            "conversation_context": self.conversation_context,
            "topics": json.dumps(self.topics, ensure_ascii=False),
            "sentiment": self.sentiment,
            "source_file": self.source_file,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_metadata(cls, doc_id: str, metadata: Dict[str, Any]) -> "ConversationDocument":
        """Create from ChromaDB metadata."""
        return cls(
            id=doc_id,
            persona_id=metadata.get("persona_id", 0),
            user_message=metadata.get("user_message", ""),
            assistant_response=metadata.get("assistant_response", ""),
            conversation_context=metadata.get("conversation_context", ""),
            topics=json.loads(metadata.get("topics", "[]")),
            sentiment=metadata.get("sentiment", ""),
            source_file=metadata.get("source_file", ""),
            created_at=metadata.get("created_at", datetime.utcnow().isoformat())
        )


class ChromaService:
    """
    Service for managing conversation embeddings using ChromaDB.
    
    This provides:
    - Vector storage of conversation pairs
    - Semantic similarity search
    - Efficient retrieval of similar past conversations
    """
    
    def __init__(
        self,
        persist_directory: str = None,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        collection_name: str = "conversations"
    ):
        """
        Initialize ChromaDB service.
        
        Args:
            persist_directory: Directory to persist ChromaDB data
            model_name: Sentence transformer model for embeddings
            collection_name: Name of the ChromaDB collection
        """
        self.model_name = model_name
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.embedding_model = None
        self.is_initialized = False
        
        # Set default persist directory
        if persist_directory is None:
            persist_directory = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "chroma_db"
            )
        self.persist_directory = persist_directory
        
        # Check availability
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB is not installed. Install with: pip install chromadb")
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers is not installed")
    
    def initialize(self) -> None:
        """
        初始化 ChromaDB 客户端和集合
        
        使用新的 ChromaDB 客户端 API（v0.4.22+）
        旧版的 Settings 配置方式已弃用，改为使用 PersistentClient
        """
        if self.is_initialized:
            return
        
        print(f"[ChromaDB] 正在初始化，数据持久化目录: {self.persist_directory}")
        
        # 创建持久化目录（如果不存在）
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # 使用新的 ChromaDB API：PersistentClient 替代已弃用的 Client + Settings
        # 这是 ChromaDB v0.4.0+ 推荐的方式
        try:
            # 尝试使用新的 PersistentClient API
            self.client = chromadb.PersistentClient(
                path=self.persist_directory
            )
            print("[ChromaDB] 使用 PersistentClient 成功创建客户端")
        except AttributeError:
            # 如果 PersistentClient 不可用，回退到旧版 API
            print("[ChromaDB] PersistentClient 不可用，回退到旧版 API")
            self.client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.persist_directory
            ))
        
        # 获取或创建集合
        # 使用 cosine 相似度度量，适合语义搜索
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
        )
        
        # 延迟加载句子嵌入模型，避免在启动时阻塞
        # paraphrase-multilingual-MiniLM-L12-v2 支持多语言，384维向量
        self.embedding_model = None
        
        self.is_initialized = True
        count = self.collection.count()
        print(f"[ChromaDB] 初始化成功！集合中共有 {count} 个文档")
    
    def _load_embedding_model(self):
        """延迟加载嵌入模型"""
        if self.embedding_model is None:
            print(f"[ChromaDB] 正在加载嵌入模型: {self.model_name}")
            self.embedding_model = SentenceTransformer(self.model_name)
            print(f"[ChromaDB] 嵌入模型加载完成")
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        生成文本的嵌入向量
        
        使用延迟加载的嵌入模型，避免在初始化时阻塞
        """
        if not self.is_initialized:
            raise RuntimeError("ChromaDB 服务未初始化")
        
        # 延迟加载嵌入模型（如果尚未加载）
        self._load_embedding_model()
        
        embedding = self.embedding_model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def _generate_document_id(self, persona_id: int, user_message: str, assistant_response: str) -> str:
        """Generate unique document ID."""
        content = f"{persona_id}:{user_message}:{assistant_response}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def add_conversation(
        self,
        persona_id: int,
        user_message: str,
        assistant_response: str,
        conversation_context: str = "",
        topics: List[str] = None,
        sentiment: str = "neutral",
        source_file: str = ""
    ) -> str:
        """
        Add a conversation pair to the vector store.
        
        Args:
            persona_id: ID of the persona
            user_message: User's message
            assistant_response: Assistant's response
            conversation_context: Previous conversation context
            topics: List of topics
            sentiment: Sentiment of the conversation
            source_file: Source file of the conversation
        
        Returns:
            Document ID
        """
        if not self.is_initialized:
            self.initialize()
        
        # Generate document ID
        doc_id = self._generate_document_id(persona_id, user_message, assistant_response)
        
        # Create document
        doc = ConversationDocument(
            id=doc_id,
            persona_id=persona_id,
            user_message=user_message,
            assistant_response=assistant_response,
            conversation_context=conversation_context,
            topics=topics or [],
            sentiment=sentiment,
            source_file=source_file,
            created_at=datetime.utcnow().isoformat()
        )
        
        # Generate embedding for user message (what we'll search against)
        embedding = self._generate_embedding(user_message)
        
        # Add to collection
        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[doc.to_metadata()],
            documents=[user_message]  # Store user message as the document text
        )
        
        print(f"[ChromaDB] Added conversation: {doc_id[:8]}... for persona {persona_id}")
        return doc_id
    
    def add_conversations_batch(
        self,
        conversations: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Add multiple conversations in batch.
        
        Args:
            conversations: List of conversation dictionaries
        
        Returns:
            List of document IDs
        """
        if not self.is_initialized:
            self.initialize()
        
        if not conversations:
            return []
        
        ids = []
        embeddings = []
        metadatas = []
        documents = []
        
        for conv in conversations:
            persona_id = conv.get("persona_id", 0)
            user_message = conv.get("user_message", "")
            assistant_response = conv.get("assistant_response", "")
            
            doc_id = self._generate_document_id(persona_id, user_message, assistant_response)
            
            doc = ConversationDocument(
                id=doc_id,
                persona_id=persona_id,
                user_message=user_message,
                assistant_response=assistant_response,
                conversation_context=conv.get("conversation_context", ""),
                topics=conv.get("topics", []),
                sentiment=conv.get("sentiment", "neutral"),
                source_file=conv.get("source_file", ""),
                created_at=datetime.utcnow().isoformat()
            )
            
            embedding = self._generate_embedding(user_message)
            
            ids.append(doc_id)
            embeddings.append(embedding)
            metadatas.append(doc.to_metadata())
            documents.append(user_message)
        
        # Batch add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
        
        print(f"[ChromaDB] Added {len(ids)} conversations in batch")
        return ids
    
    def search_similar_conversations(
        self,
        query: str,
        persona_id: Optional[int] = None,
        top_k: int = 5,
        score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Search for similar conversations.
        
        Args:
            query: Search query (user message)
            persona_id: Optional filter by persona
            top_k: Number of results to return
            score_threshold: Minimum similarity score (0-1)
        
        Returns:
            List of similar conversations with scores
        """
        if not self.is_initialized:
            self.initialize()
        
        # Generate query embedding
        query_embedding = self._generate_embedding(query)
        
        # Build where filter if persona_id specified
        where_filter = None
        if persona_id is not None:
            where_filter = {"persona_id": persona_id}
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["metadatas", "distances", "documents"]
        )
        
        # Format results
        similar_conversations = []
        
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i]
                metadata = results["metadatas"][0][i]
                
                # Convert distance to similarity score (cosine distance to similarity)
                similarity = 1 - distance
                
                if similarity >= score_threshold:
                    doc = ConversationDocument.from_metadata(doc_id, metadata)
                    similar_conversations.append({
                        "id": doc_id,
                        "user_message": doc.user_message,
                        "assistant_response": doc.assistant_response,
                        "conversation_context": doc.conversation_context,
                        "topics": doc.topics,
                        "sentiment": doc.sentiment,
                        "similarity_score": similarity,
                        "persona_id": doc.persona_id
                    })
        
        return similar_conversations
    
    def get_conversation_by_id(self, doc_id: str) -> Optional[ConversationDocument]:
        """Get a specific conversation by ID."""
        if not self.is_initialized:
            self.initialize()
        
        try:
            result = self.collection.get(
                ids=[doc_id],
                include=["metadatas"]
            )
            
            if result["ids"]:
                metadata = result["metadatas"][0]
                return ConversationDocument.from_metadata(doc_id, metadata)
            
            return None
        except Exception as e:
            print(f"[ChromaDB] Error getting conversation: {e}")
            return None
    
    def get_conversations_by_persona(
        self,
        persona_id: int,
        limit: int = 100
    ) -> List[ConversationDocument]:
        """Get all conversations for a specific persona."""
        if not self.is_initialized:
            self.initialize()
        
        results = self.collection.get(
            where={"persona_id": persona_id},
            limit=limit,
            include=["metadatas"]
        )
        
        documents = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i]
                documents.append(ConversationDocument.from_metadata(doc_id, metadata))
        
        return documents
    
    def delete_conversation(self, doc_id: str) -> bool:
        """Delete a conversation by ID."""
        if not self.is_initialized:
            self.initialize()
        
        try:
            self.collection.delete(ids=[doc_id])
            print(f"[ChromaDB] Deleted conversation: {doc_id[:8]}...")
            return True
        except Exception as e:
            print(f"[ChromaDB] Error deleting conversation: {e}")
            return False
    
    def delete_persona_conversations(self, persona_id: int) -> bool:
        """Delete all conversations for a persona."""
        if not self.is_initialized:
            self.initialize()
        
        try:
            self.collection.delete(where={"persona_id": persona_id})
            print(f"[ChromaDB] Deleted all conversations for persona {persona_id}")
            return True
        except Exception as e:
            print(f"[ChromaDB] Error deleting persona conversations: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection."""
        if not self.is_initialized:
            self.initialize()
        
        count = self.collection.count()
        
        return {
            "initialized": self.is_initialized,
            "collection_name": self.collection_name,
            "persist_directory": self.persist_directory,
            "total_documents": count,
            "embedding_model": self.model_name
        }
    
    def persist(self) -> None:
        """Persist the database to disk."""
        if self.is_initialized and self.client:
            # ChromaDB with duckdb+parquet persists automatically
            # This is here for compatibility
            pass
    
    def get_conversation_context_for_prompt(
        self,
        query: str,
        persona_id: int,
        num_examples: int = 3
    ) -> str:
        """
        Get formatted conversation examples for system prompt.
        
        Returns a string of similar conversation pairs that can
        be used as few-shot examples.
        """
        similar = self.search_similar_conversations(
            query=query,
            persona_id=persona_id,
            top_k=num_examples
        )
        
        if not similar:
            return ""
        
        parts = ["\n参考相似对话："]
        for i, conv in enumerate(similar, 1):
            user_msg = conv.get('user_message', '')
            response = conv.get('assistant_response', '')
            
            # Truncate if too long
            if len(user_msg) > 100:
                user_msg = user_msg[:100] + "..."
            if len(response) > 150:
                response = response[:150] + "..."
            
            parts.append(f"\n示例{i}：")
            parts.append(f"对方：{user_msg}")
            parts.append(f"你：{response}")
        
        return "\n".join(parts)


# Singleton instance
_chroma_service = None


def get_chroma_service(
    persist_directory: str = None,
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"
) -> ChromaService:
    """Get or create ChromaDB service singleton."""
    global _chroma_service
    if _chroma_service is None:
        _chroma_service = ChromaService(
            persist_directory=persist_directory,
            model_name=model_name
        )
        _chroma_service.initialize()
    return _chroma_service


if __name__ == "__main__":
    # Test the service
    print("Testing ChromaDB Service...")
    
    service = get_chroma_service()
    
    # Test adding conversations
    test_conversations = [
        {
            "persona_id": 1,
            "user_message": "今天天气真好啊",
            "assistant_response": "是啊，阳光明媚，适合出去走走~",
            "topics": ["天气"],
            "sentiment": "happy"
        },
        {
            "persona_id": 1,
            "user_message": "我有点难过",
            "assistant_response": "抱抱你，发生什么事了吗？",
            "topics": ["情绪"],
            "sentiment": "sad"
        },
        {
            "persona_id": 1,
            "user_message": "周末有什么安排？",
            "assistant_response": "还没想好呢，你有什么建议吗？",
            "topics": ["计划"],
            "sentiment": "neutral"
        }
    ]
    
    # Add batch
    ids = service.add_conversations_batch(test_conversations)
    print(f"\nAdded {len(ids)} conversations")
    
    # Test search
    print("\nSearching for similar conversations...")
    results = service.search_similar_conversations(
        query="今天天气不错",
        persona_id=1,
        top_k=2
    )
    
    for r in results:
        print(f"\nScore: {r['similarity_score']:.3f}")
        print(f"User: {r['user_message']}")
        print(f"Assistant: {r['assistant_response']}")
    
    # Test prompt context
    print("\n\nPrompt context:")
    context = service.get_conversation_context_for_prompt(
        query="今天天气不错",
        persona_id=1,
        num_examples=2
    )
    print(context)
    
    # Stats
    print("\n\nStats:")
    print(service.get_stats())
