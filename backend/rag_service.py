"""
RAG (Retrieval-Augmented Generation) Service for Emoji Chatbot.

This module provides the core functionality for:
1. Loading and processing emoji data from JSONL files
2. Generating embeddings using sentence-transformers
3. Storing and searching vectors using FAISS
4. Retrieving relevant emojis based on user queries
5. Retrieving similar past conversations for persona mimicry
"""

import os
# 设置 HuggingFace 离线模式，强制使用缓存模型
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

import json
import re
from typing import List, Dict, Any, Optional
import numpy as np

# Try to import optional dependencies
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("[RAG] Warning: faiss not available, using fallback search")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("[RAG] Warning: sentence-transformers not available, using fallback embeddings")


class RAGService:
    """
    RAG Service for emoji retrieval and conversation search.

    This class handles:
    - Loading emoji data from JSONL files
    - Generating embeddings for text descriptions
    - Building and querying FAISS index for similarity search
    - Searching similar past conversations for digital twin
    """

    def __init__(
        self,
        jsonl_path: str = "./emoji_classification.jsonl",
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        embedding_dim: int = 384
    ):
        """
        Initialize the RAG Service.

        Args:
            jsonl_path: Path to the emoji classification JSONL file
            model_name: Name of the sentence-transformers model to use
            embedding_dim: Dimension of the embedding vectors
        """
        self.jsonl_path = jsonl_path
        self.model_name = model_name
        self.embedding_dim = embedding_dim

        # Initialize components
        self.model = None
        self.index = None
        self.emoji_data: List[Dict[str, Any]] = []
        self.is_initialized = False
        self.use_fallback = not (FAISS_AVAILABLE and SENTENCE_TRANSFORMERS_AVAILABLE)

        # Simple keyword-based embeddings for fallback mode
        self.keyword_embeddings: Dict[str, np.ndarray] = {}

        # Conversation search components
        self.conversation_index = None
        self.conversation_data: List[Dict[str, Any]] = []
        self.conversation_embeddings = None

    def _load_model(self) -> None:
        """Load the sentence-transformers model or use fallback."""
        if self.use_fallback:
            print("[RAG] Using fallback keyword-based embeddings (sentence-transformers not available)")
            return

        print(f"[RAG] Loading embedding model: {self.model_name}")
        try:
            self.model = SentenceTransformer(self.model_name)
            print(f"[RAG] Model loaded successfully")
        except Exception as e:
            print(f"[RAG] Error loading model: {e}")
            print("[RAG] Falling back to keyword-based embeddings")
            self.use_fallback = True

    def _load_emoji_data(self) -> None:
        """Load emoji data from the JSONL file."""
        print(f"[RAG] Loading emoji data from: {self.jsonl_path}")

        if not os.path.exists(self.jsonl_path):
            raise FileNotFoundError(f"Emoji data file not found: {self.jsonl_path}")

        self.emoji_data = []
        line_count = 0
        error_count = 0

        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                line_count += 1
                try:
                    item = json.loads(line)
                    # Validate required fields
                    if 'file_name' in item and 'description' in item:
                        self.emoji_data.append(item)
                    else:
                        print(f"[RAG] Warning: Missing required fields at line {line_count}")
                        error_count += 1
                except json.JSONDecodeError as e:
                    print(f"[RAG] Error parsing JSON at line {line_count}: {e}")
                    error_count += 1

        print(f"[RAG] Loaded {len(self.emoji_data)} emojis (errors: {error_count})")

    def _build_index(self) -> None:
        """Build the FAISS index for similarity search or prepare fallback keywords."""
        if not self.emoji_data:
            raise RuntimeError("No emoji data loaded. Call _load_emoji_data() first.")

        if self.use_fallback:
            print(f"[RAG] Building keyword index for {len(self.emoji_data)} emojis...")
            # Build keyword-based embeddings
            self.keyword_embeddings = {}
            for i, item in enumerate(self.emoji_data):
                keywords = self._extract_keywords(item)
                self.keyword_embeddings[i] = keywords
            print(f"[RAG] Keyword index built successfully")
            return

        if not self.model:
            raise RuntimeError("Model not loaded. Call _load_model() first.")

        print(f"[RAG] Building FAISS index for {len(self.emoji_data)} emojis...")

        # Prepare texts for embedding
        texts = []
        for item in self.emoji_data:
            description = item.get('description', '')
            sub_category = item.get('sub_category', '')
            # Combine both fields with weight
            combined = f"{sub_category}: {description}" if sub_category else description
            texts.append(combined)

        # Generate embeddings
        print(f"[RAG] Generating embeddings for {len(texts)} texts...")
        try:
            embeddings = self.model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=True,
                batch_size=32
            )
            print(f"[RAG] Embeddings shape: {embeddings.shape}")

            # Normalize embeddings for cosine similarity
            faiss.normalize_L2(embeddings)

            # Create FAISS index
            print(f"[RAG] Creating FAISS index with dim={self.embedding_dim}...")
            self.index = faiss.IndexFlatIP(self.embedding_dim)

            # Add vectors to index
            print(f"[RAG] Adding vectors to index...")
            self.index.add(embeddings.astype('float32'))

            print(f"[RAG] Index built successfully. Total vectors: {self.index.ntotal}")
        except Exception as e:
            print(f"[RAG] Error building index: {e}")
            import traceback
            print(f"[RAG] Traceback: {traceback.format_exc()}")
            raise

    def _extract_keywords(self, item: Dict[str, Any]) -> set:
        """Extract keywords from emoji item for fallback mode."""
        keywords = set()

        # Extract from description
        description = item.get('description', '')
        if description:
            # Simple word extraction
            words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', description.lower())
            keywords.update(words)

        # Add category keywords
        category = item.get('sub_category', '')
        if category:
            keywords.add(category.lower())

        return keywords

    def initialize(self) -> None:
        """Initialize the RAG service."""
        if self.is_initialized:
            print("[RAG] Already initialized")
            return

        print("[RAG] Initializing service...")
        self._load_model()
        self._load_emoji_data()
        self._build_index()
        self.is_initialized = True
        print("[RAG] Initialization complete!")

    def search(
        self,
        query: str,
        top_k: int = 3,
        score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant emojis based on a text query.

        Args:
            query: The search query text
            top_k: Number of results to return
            score_threshold: Minimum similarity score

        Returns:
            List of matching emojis with similarity scores
        """
        if not self.is_initialized:
            raise RuntimeError("Service not initialized. Call initialize() first.")
        if not query or not query.strip():
            return []

        # Use fallback search if in fallback mode
        if self.use_fallback:
            return self._fallback_search(query, top_k, score_threshold)

        # Generate embedding for query
        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True
        )

        # Normalize for cosine similarity
        faiss.normalize_L2(query_embedding)

        # Search FAISS index
        distances, indices = self.index.search(
            query_embedding.astype('float32'),
            k=min(top_k, self.index.ntotal)
        )

        # Format results
        results = []
        for i, (score, idx) in enumerate(zip(distances[0], indices[0])):
            if idx == -1:
                continue
            if score < score_threshold:
                continue

            result = self.emoji_data[idx].copy()
            result['score'] = float(score)
            result['rank'] = i + 1
            results.append(result)

        return results

    def _fallback_search(self, query: str, top_k: int = 3, score_threshold: float = 0.1) -> List[Dict[str, Any]]:
        """
        Fallback search using keyword matching when FAISS/sentence-transformers unavailable.
        """
        import re

        # Extract query keywords (支持中文、英文、数字)
        query_keywords = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|\d+', query.lower()))
        if not query_keywords:
            return []

        print(f"[RAG Fallback] Searching with keywords: {query_keywords}")

        # Score each emoji by keyword overlap
        scores = []
        for idx, item in enumerate(self.emoji_data):
            emoji_keywords = self.keyword_embeddings.get(idx, set())
            if not emoji_keywords:
                continue

            # Calculate simple overlap score
            intersection = query_keywords & emoji_keywords
            if not intersection:
                continue

            # 只要有匹配就给分，匹配越多分数越高
            score = len(intersection) / max(len(query_keywords), 1)
            scores.append((score, idx, item, intersection))

        # Sort by score and return top_k
        scores.sort(reverse=True, key=lambda x: x[0])

        print(f"[RAG Fallback] Found {len(scores)} matches")

        results = []
        for i, (score, idx, item, matched) in enumerate(scores[:top_k]):
            result = item.copy()
            result['score'] = float(score)
            result['rank'] = i + 1
            results.append(result)
            print(f"[RAG Fallback] Match {i+1}: {item.get('file_name', '')} - score: {score:.3f}, matched: {matched}")

        return results

    def get_random_emoji(self) -> Optional[Dict[str, Any]]:
        """Get a random emoji from the dataset."""
        if not self.emoji_data:
            return None
        import random
        return random.choice(self.emoji_data).copy()

    def get_emoji_by_md5(self, md5: str) -> Optional[Dict[str, Any]]:
        """
        Get emoji information by MD5 hash.

        Args:
            md5: The MD5 hash of the emoji file (without extension)

        Returns:
            Emoji information dict or None if not found
        """
        if not self.emoji_data:
            return None

        for emoji in self.emoji_data:
            file_name = emoji.get('file_name', '')
            # Remove extension to get MD5
            emoji_md5 = file_name.replace('.gif', '').replace('.png', '')
            if emoji_md5 == md5:
                return emoji.copy()

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the RAG service."""
        return {
            "initialized": self.is_initialized,
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "total_emojis": len(self.emoji_data),
            "indexed_vectors": self.index.ntotal if self.index else 0
        }


class ConversationRAGService:
    """
    RAG Service for retrieving similar past conversations.
    
    This helps the digital twin find similar past interactions
    to guide its response style and content.
    
    Now uses ChromaDB as the primary storage for better
    semantic search capabilities.
    """
    
    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        embedding_dim: int = 384,
        use_chroma: bool = True
    ):
        self.model_name = model_name
        self.embedding_dim = embedding_dim
        self.model = None
        self.index = None
        self.conversations: List[Dict[str, Any]] = []
        self.is_initialized = False
        self.use_fallback = not (FAISS_AVAILABLE and SENTENCE_TRANSFORMERS_AVAILABLE)
        self.use_chroma = use_chroma
        
        # ChromaDB service
        self.chroma_service = None
        
        # Keyword index for fallback
        self.keyword_index: Dict[int, set] = {}
    
    def initialize(self) -> None:
        """Initialize the conversation RAG service."""
        if self.is_initialized:
            return
        
        # Try to use ChromaDB first
        if self.use_chroma:
            try:
                from chroma_service import get_chroma_service
                self.chroma_service = get_chroma_service()
                print("[ConversationRAG] Using ChromaDB for conversation storage")
                self.is_initialized = True
                return
            except Exception as e:
                print(f"[ConversationRAG] ChromaDB not available: {e}")
                print("[ConversationRAG] Falling back to FAISS/keyword search")
        
        # Fallback to FAISS
        if not self.use_fallback:
            try:
                print(f"[ConversationRAG] Loading model: {self.model_name}")
                self.model = SentenceTransformer(self.model_name)
                print("[ConversationRAG] Model loaded successfully")
            except Exception as e:
                print(f"[ConversationRAG] Error loading model: {e}")
                self.use_fallback = True
        
        self.is_initialized = True
    
    def build_conversation_index(
        self,
        conversations: List[Dict[str, Any]]
    ) -> None:
        """
        Build index from conversation pairs.
        
        Args:
            conversations: List of conversation pairs with format:
                {
                    'user_message': str,
                    'assistant_response': str,
                    'context': str (optional),
                    'topics': List[str] (optional),
                    'sentiment': str (optional)
                }
        """
        if not self.is_initialized:
            self.initialize()
        
        self.conversations = conversations
        
        if not conversations:
            print("[ConversationRAG] No conversations to index")
            return
        
        if self.use_fallback:
            self._build_keyword_index()
        else:
            self._build_vector_index()
    
    def _build_keyword_index(self) -> None:
        """Build keyword-based index for fallback mode."""
        print(f"[ConversationRAG] Building keyword index for {len(self.conversations)} conversations...")
        
        self.keyword_index = {}
        for i, conv in enumerate(self.conversations):
            text = f"{conv.get('user_message', '')} {conv.get('assistant_response', '')}"
            keywords = set(re.findall(r'[\u4e00-\u9fff]+', text))
            self.keyword_index[i] = keywords
        
        print("[ConversationRAG] Keyword index built successfully")
    
    def _build_vector_index(self) -> None:
        """Build FAISS vector index."""
        print(f"[ConversationRAG] Building vector index for {len(self.conversations)} conversations...")
        
        # Prepare texts (combine user message and context)
        texts = []
        for conv in self.conversations:
            user_msg = conv.get('user_message', '')
            context = conv.get('context', '')
            # Give more weight to user message
            combined = f"{user_msg} {user_msg} {context}"
            texts.append(combined)
        
        try:
            # Generate embeddings
            embeddings = self.model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=True,
                batch_size=32
            )
            
            # Normalize
            faiss.normalize_L2(embeddings)
            
            # Create index
            self.index = faiss.IndexFlatIP(self.embedding_dim)
            self.index.add(embeddings.astype('float32'))
            
            print(f"[ConversationRAG] Index built with {self.index.ntotal} vectors")
        except Exception as e:
            print(f"[ConversationRAG] Error building index: {e}")
            self.use_fallback = True
            self._build_keyword_index()
    
    def search_similar_conversations(
        self,
        query: str,
        persona_id: Optional[int] = None,
        top_k: int = 5,
        score_threshold: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Search for similar past conversations.
        
        Args:
            query: The current user message
            persona_id: Optional filter by persona ID
            top_k: Number of results to return
            score_threshold: Minimum similarity score
        
        Returns:
            List of similar conversation pairs
        """
        if not self.is_initialized:
            raise RuntimeError("Service not initialized")
        
        # Use ChromaDB if available
        if self.chroma_service:
            return self.chroma_service.search_similar_conversations(
                query=query,
                persona_id=persona_id,
                top_k=top_k,
                score_threshold=score_threshold
            )
        
        # Fallback to local index
        if not self.conversations:
            return []
        
        if self.use_fallback:
            return self._fallback_conversation_search(query, top_k, score_threshold)
        else:
            return self._vector_conversation_search(query, top_k, score_threshold)
    
    def _vector_conversation_search(
        self,
        query: str,
        top_k: int,
        score_threshold: float
    ) -> List[Dict[str, Any]]:
        """Search using vector similarity."""
        # Generate query embedding
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)
        
        # Search
        distances, indices = self.index.search(
            query_embedding.astype('float32'),
            k=min(top_k, self.index.ntotal)
        )
        
        # Format results
        results = []
        for score, idx in zip(distances[0], indices[0]):
            if idx == -1 or score < score_threshold:
                continue
            
            result = self.conversations[idx].copy()
            result['similarity_score'] = float(score)
            results.append(result)
        
        return results
    
    def _fallback_conversation_search(
        self,
        query: str,
        top_k: int,
        score_threshold: float
    ) -> List[Dict[str, Any]]:
        """Search using keyword matching."""
        query_keywords = set(re.findall(r'[\u4e00-\u9fff]+', query))
        if not query_keywords:
            return []
        
        # Score conversations
        scores = []
        for idx, conv in enumerate(self.conversations):
            conv_keywords = self.keyword_index.get(idx, set())
            if not conv_keywords:
                continue
            
            intersection = query_keywords & conv_keywords
            if not intersection:
                continue
            
            score = len(intersection) / max(len(query_keywords), 1)
            scores.append((score, idx))
        
        # Sort and return top results
        scores.sort(reverse=True, key=lambda x: x[0])
        
        results = []
        for score, idx in scores[:top_k]:
            if score < score_threshold:
                continue
            result = self.conversations[idx].copy()
            result['similarity_score'] = float(score)
            results.append(result)
        
        return results
    
    def get_conversation_context_for_prompt(
        self,
        query: str,
        persona_id: Optional[int] = None,
        num_examples: int = 3
    ) -> str:
        """
        Get formatted conversation examples for system prompt.
        
        Returns a string of similar conversation pairs that can
        be used as few-shot examples.
        
        Args:
            query: The search query
            persona_id: Optional persona ID to filter by
            num_examples: Number of examples to include
        """
        # Use ChromaDB if available
        if self.chroma_service:
            return self.chroma_service.get_conversation_context_for_prompt(
                query=query,
                persona_id=persona_id,
                num_examples=num_examples
            )
        
        # Fallback to local search
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
    
    def add_conversation(self, conversation: Dict[str, Any]) -> None:
        """Add a new conversation to the index."""
        self.conversations.append(conversation)
        
        # Rebuild index with new conversation
        if self.use_fallback:
            idx = len(self.conversations) - 1
            text = f"{conversation.get('user_message', '')} {conversation.get('assistant_response', '')}"
            keywords = set(re.findall(r'[\u4e00-\u9fff]+', text))
            self.keyword_index[idx] = keywords
        else:
            # For vector index, we need to rebuild
            self._build_vector_index()


# Singleton instances
_rag_service = None
_conversation_rag_service = None


def get_rag_service(jsonl_path: str = "./emoji_classification.jsonl") -> RAGService:
    """Get or create RAG service singleton."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService(jsonl_path=jsonl_path)
    return _rag_service


def get_conversation_rag_service() -> ConversationRAGService:
    """Get or create conversation RAG service singleton."""
    global _conversation_rag_service
    if _conversation_rag_service is None:
        _conversation_rag_service = ConversationRAGService()
    return _conversation_rag_service


if __name__ == "__main__":
    # Test the services
    print("Testing RAG Service...")
    
    # Test emoji RAG
    rag = get_rag_service()
    rag.initialize()
    
    # Test search
    results = rag.search("开心", top_k=3)
    print(f"\nSearch results for '开心':")
    for r in results:
        print(f"  - {r.get('sub_category')}: {r.get('description', '')[:50]}...")
    
    # Test conversation RAG
    print("\n\nTesting Conversation RAG Service...")
    conv_rag = get_conversation_rag_service()
    
    # Sample conversations
    sample_convs = [
        {
            'user_message': '今天天气真好啊',
            'assistant_response': '是啊，阳光明媚，适合出去走走~',
            'topics': ['天气'],
            'sentiment': 'happy'
        },
        {
            'user_message': '我有点难过',
            'assistant_response': '抱抱你，发生什么事了吗？',
            'topics': ['情绪'],
            'sentiment': 'sad'
        },
        {
            'user_message': '周末有什么安排？',
            'assistant_response': '还没想好呢，你有什么建议吗？',
            'topics': ['计划'],
            'sentiment': 'neutral'
        }
    ]
    
    conv_rag.build_conversation_index(sample_convs)
    
    # Test search
    similar = conv_rag.search_similar_conversations("今天天气不错", top_k=2)
    print(f"\nSimilar conversations for '今天天气不错':")
    for s in similar:
        print(f"  - User: {s.get('user_message')}")
        print(f"    Response: {s.get('assistant_response')}")
        print(f"    Score: {s.get('similarity_score', 0):.3f}")
