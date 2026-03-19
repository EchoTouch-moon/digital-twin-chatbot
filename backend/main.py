"""
数字孪生对话智能体 - FastAPI 后端服务

本项目是一个基于 RAG（检索增强生成）的数字孪生对话系统，主要功能包括：
- 智能表情包检索与推荐
- 数字孪生角色管理（模仿特定人物的说话风格）
- 聊天记录导入与处理
- 长期记忆系统
- 健康检查与监控
- 静态文件服务（表情包图片）

技术栈：
- FastAPI: 高性能异步 Web 框架
- ChromaDB: 向量数据库存储对话嵌入
- SQLAlchemy: ORM 数据库操作
- Sentence-Transformers: 文本嵌入生成
- FAISS: 快速相似度搜索
"""

import os
import sys
import json
import time
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

# 设置 HuggingFace 离线模式，强制使用缓存模型
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# 加载环境变量配置文件
from dotenv import load_dotenv

# 将当前目录添加到 Python 路径，确保可以导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 获取项目根目录（backend 的父目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 从项目根目录加载 .env 文件
# override=True 确保 .env 文件中的配置优先于系统环境变量
load_dotenv(os.path.join(PROJECT_ROOT, '.env'), override=True)

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag_service import RAGService, get_conversation_rag_service
from llm_service import LLMService, LLMConfig

# Import emoji behavior service
try:
    from emoji_behavior_service import get_emoji_behavior_service, EmojiBehaviorService
    EMOJI_BEHAVIOR_AVAILABLE = True
except ImportError:
    EMOJI_BEHAVIOR_AVAILABLE = False
    print("[Startup] Warning: Emoji behavior service not available")

# Import session service
try:
    from session_service import get_session_service
    SESSION_SERVICE_AVAILABLE = True
except ImportError:
    SESSION_SERVICE_AVAILABLE = False
    print("[Startup] Warning: Session service not available")

# Import dynamic prompt service
try:
    from dynamic_prompt_service import get_dynamic_prompt_service
    DYNAMIC_PROMPT_AVAILABLE = True
except ImportError:
    DYNAMIC_PROMPT_AVAILABLE = False
    print("[Startup] Warning: Dynamic prompt service not available")

# Import advanced memory service
try:
    from advanced_memory_service import get_advanced_memory_service
    ADVANCED_MEMORY_AVAILABLE = True
except ImportError:
    ADVANCED_MEMORY_AVAILABLE = False
    print("[Startup] Warning: Advanced memory service not available")

# Import prompt truncator
try:
    from prompt_truncator import get_prompt_truncator
    PROMPT_TRUNCATOR_AVAILABLE = True
except ImportError:
    PROMPT_TRUNCATOR_AVAILABLE = False
    print("[Startup] Warning: Prompt truncator not available")

# 导入异步任务支持
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

# 线程池用于后台学习任务
learning_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="learner")

# 线程池用于记忆巩固任务（独立于学习任务）
memory_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory")


# ==================== 持续学习后台任务 ====================

def run_continuous_learning(persona_id: int):
    """
    在后台线程中执行持续学习

    这是异步执行的，不会阻塞主请求

    重要：使用独立的数据库Session，避免多线程共享Session导致的死锁问题
    """
    # 使用独立的Session，确保线程安全
    from database import SessionLocal

    db = None
    try:
        print(f"[Learning] Starting continuous learning for persona {persona_id}...")

        # 创建独立的Session
        db = SessionLocal()

        # 使用独立Session创建服务实例
        from dynamic_prompt_service import DynamicPromptService
        dynamic_svc = DynamicPromptService(db)

        if dynamic_svc:
            result = dynamic_svc.learn_and_update(persona_id)

            if result and 'updates' in result and result['updates']:
                print(f"[Learning] Updated persona {persona_id}: {result['updates']}")
            else:
                print(f"[Learning] No updates needed for persona {persona_id}")

    except Exception as e:
        print(f"[Learning] Error in continuous learning: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保关闭Session
        if db:
            try:
                db.close()
                print(f"[Learning] Database session closed for persona {persona_id}")
            except Exception as e:
                print(f"[Learning] Error closing session: {e}")


def trigger_learning_if_needed(persona_id: int) -> bool:
    """
    检查是否需要触发持续学习，并在需要时异步执行

    Args:
        persona_id: Persona ID

    Returns:
        是否触发了学习
    """
    global conversation_counters

    # 增加计数器
    conversation_counters[persona_id] = conversation_counters.get(persona_id, 0) + 1
    count = conversation_counters[persona_id]

    # 检查是否达到触发阈值
    if count % LEARNING_INTERVAL == 0:
        print(f"[Learning] Trigger threshold reached ({count} conversations), starting learning...")

        # 异步执行学习任务
        learning_executor.submit(run_continuous_learning, persona_id)
        return True

    return False


# ==================== 记忆巩固后台任务 ====================

def run_memory_consolidation(persona_id: int, new_memory_content: str = None):
    """
    在后台线程中执行记忆巩固

    包括：冲突检测、记忆合并、热记忆提升等耗时操作

    重要：使用独立的数据库Session
    """
    from database import SessionLocal

    db = None
    try:
        print(f"[MemoryConsolidation] Starting for persona {persona_id}...")

        # 创建独立的Session
        db = SessionLocal()

        from advanced_memory_service import AdvancedMemoryService
        memory_svc = AdvancedMemoryService(db)

        tasks_completed = []

        # 1. 检查并提升热记忆
        try:
            promoted = memory_svc.check_and_promote_memories(persona_id)
            if promoted > 0:
                tasks_completed.append(f"promoted {promoted} hot memories")
        except Exception as e:
            print(f"[MemoryConsolidation] Error promoting memories: {e}")

        # 2. 合并相似记忆
        try:
            merged = memory_svc.merge_similar_memories(persona_id, threshold=0.9)
            if merged > 0:
                tasks_completed.append(f"merged {merged} memories")
        except Exception as e:
            print(f"[MemoryConsolidation] Error merging memories: {e}")

        # 3. 清理过期的Scratchpad
        try:
            cleaned = memory_svc.cleanup_expired_scratchpads()
            if cleaned > 0:
                tasks_completed.append(f"cleaned {cleaned} scratchpads")
        except Exception as e:
            print(f"[MemoryConsolidation] Error cleaning scratchpads: {e}")

        # 4. 如果有新记忆内容，检测冲突
        if new_memory_content:
            try:
                result = memory_svc.detect_and_resolve_conflict(persona_id, new_memory_content)
                if result.get("has_conflict"):
                    tasks_completed.append("resolved memory conflict")
            except Exception as e:
                print(f"[MemoryConsolidation] Error detecting conflicts: {e}")

        if tasks_completed:
            print(f"[MemoryConsolidation] Completed for persona {persona_id}: {', '.join(tasks_completed)}")
        else:
            print(f"[MemoryConsolidation] No updates needed for persona {persona_id}")

    except Exception as e:
        print(f"[MemoryConsolidation] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保关闭Session
        if db:
            try:
                db.close()
            except Exception:
                pass


def run_journal_generation(persona_id: int, date_str: str = None, journal_type: str = "daily"):
    """
    在后台线程中生成日记

    Args:
        persona_id: Persona ID
        date_str: 日期字符串 (YYYY-MM-DD)，可选
        journal_type: "daily" 或 "weekly"
    """
    from database import SessionLocal

    db = None
    try:
        print(f"[JournalGen] Starting {journal_type} journal generation for persona {persona_id}...")

        db = SessionLocal()

        from advanced_memory_service import AdvancedMemoryService
        from datetime import datetime

        memory_svc = AdvancedMemoryService(db)

        # 解析日期
        journal_date = None
        if date_str:
            try:
                journal_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass

        # 生成日记
        if journal_type == "weekly":
            journal = memory_svc.generate_weekly_journal(persona_id, journal_date)
        else:
            journal = memory_svc.generate_daily_journal(persona_id, journal_date)

        if journal:
            print(f"[JournalGen] Created {journal_type} journal for persona {persona_id}")
        else:
            print(f"[JournalGen] No data for {journal_type} journal for persona {persona_id}")

    except Exception as e:
        print(f"[JournalGen] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def trigger_memory_consolidation(persona_id: int, new_memory_content: str = None) -> bool:
    """
    触发记忆巩固任务（异步）

    Returns:
        是否触发了任务
    """
    try:
        memory_executor.submit(run_memory_consolidation, persona_id, new_memory_content)
        return True
    except Exception as e:
        print(f"[MemoryConsolidation] Failed to trigger: {e}")
        return False


# ==================== Pydantic 数据模型 ====================
# Pydantic 用于数据验证和序列化，FastAPI 会自动使用这些模型验证请求和响应

class ChatMessage(BaseModel):
    """
    单条聊天消息模型
    
    用于表示对话中的一条消息，包含角色（发送者）和内容
    """
    role: str = Field(..., description="消息角色: 'user'（用户）或 'assistant'（助手）")
    content: str = Field(..., description="消息内容文本")


class ChatRequest(BaseModel):
    """
    普通聊天请求模型
    
    用于基础对话接口，支持携带历史对话上下文
    """
    message: str = Field(..., description="用户输入的消息内容")
    history: Optional[List[ChatMessage]] = Field(default=None, description="可选的历史对话记录，用于保持上下文")


class PersonalizedChatRequest(BaseModel):
    """
    个性化聊天请求模型（数字孪生对话）

    用于与特定数字孪生角色对话，支持记忆功能和会话连续性
    """
    message: str = Field(default="", description="用户输入的消息内容")
    persona_id: int = Field(..., description="要对话的数字孪生角色ID")
    session_id: Optional[int] = Field(default=None, description="可选的会话ID，用于保持对话连续性")
    history: Optional[List[ChatMessage]] = Field(default=None, description="可选的历史对话记录")
    use_memory: bool = Field(default=True, description="是否使用长期记忆上下文")
    # 用户发送表情包相关字段
    user_emoji_url: Optional[str] = Field(default=None, description="用户发送的表情包URL")
    user_emoji_description: Optional[str] = Field(default=None, description="表情包的文字描述")


class ChatResponse(BaseModel):
    """
    普通聊天响应模型
    
    包含助手的文本回复和推荐的表情包信息
    """
    text: str = Field(..., description="助手的文本回复内容")
    image_url: Optional[str] = Field(default=None, description="推荐表情包图片的URL地址")
    emoji_info: Optional[dict] = Field(default=None, description="表情包的详细信息（描述、分类、相似度分数等）")


class PersonalizedChatResponse(BaseModel):
    """
    个性化聊天响应模型
    
    包含数字孪生角色的回复和相关的元数据
    """
    text: str = Field(..., description="数字孪生角色的文本回复")
    image_url: Optional[str] = Field(default=None, description="推荐表情包图片的URL地址")
    emoji_info: Optional[dict] = Field(default=None, description="表情包的详细信息")
    persona_id: int = Field(..., description="回复角色的ID")
    session_id: Optional[int] = Field(default=None, description="会话ID")
    memory_used: bool = Field(default=False, description="是否使用了记忆上下文")


class HealthResponse(BaseModel):
    """
    健康检查响应模型
    
    用于监控系统各组件的运行状态
    """
    status: str  # 整体状态: healthy（健康）或 degraded（降级）
    rag_service: dict  # RAG 服务状态
    llm_service: dict  # LLM 服务状态
    static_files: dict  # 静态文件服务状态
    database: dict  # 数据库状态
    chromadb: dict  # ChromaDB 向量数据库状态


class SearchResponse(BaseModel):
    """
    表情包搜索响应模型
    
    返回搜索结果列表和总数
    """
    query: str  # 搜索查询
    results: List[dict]  # 搜索结果列表
    total: int  # 结果总数


class PersonaCreateRequest(BaseModel):
    """
    创建数字孪生角色请求模型
    
    用于创建新的数字孪生角色（Persona）
    """
    name: str = Field(..., description="角色名称（如：小明、小红）")
    description: Optional[str] = Field(default=None, description="角色描述（性格特点、背景等）")
    avatar_url: Optional[str] = Field(default=None, description="角色头像图片的URL地址")


class PersonaResponse(BaseModel):
    """
    数字孪生角色响应模型

    包含角色的完整信息，包括性格分析结果和表情包行为画像
    """
    id: int  # 角色唯一标识符
    name: str  # 角色名称
    description: Optional[str]  # 角色描述
    avatar_url: Optional[str]  # 头像URL
    personality_traits: dict  # 性格特征（正式度、幽默度、温暖度等）
    common_phrases: List[str]  # 常用口头禅
    emoji_preferences: List[str]  # 表情包使用偏好
    # 表情包行为画像 - 新增字段
    emoji_usage_frequency: Optional[str] = "medium"  # 使用频率: high/medium/low/none
    emoji_usage_rate: Optional[float] = 0.5  # 使用率 0.0-1.0
    emoji_scenario_prefs: Optional[List[str]] = []  # 场景偏好
    emoji_type_prefs: Optional[List[str]] = []  # 类型偏好
    avg_response_length: int  # 平均回复长度（字数）
    response_style: str  # 回复风格（正式、随意、幽默等）
    created_at: str  # 创建时间
    updated_at: str  # 更新时间


class ImportChatHistoryResponse(BaseModel):
    """
    聊天记录导入响应模型
    
    返回导入操作的统计信息和分析结果
    """
    status: str  # 导入状态：success 或 error
    total_messages: int  # 导入的消息总数
    conversation_pairs: int  # 提取的对话对数（用户-助手配对）
    stored_pairs: int  # 成功存储的对话对数
    personality_traits: dict  # 自动分析的性格特征
    persona_id: int  # 关联的角色ID


class MemoryResponse(BaseModel):
    """
    记忆响应模型
    
    表示系统提取和存储的长期记忆
    """
    id: int  # 记忆唯一标识符
    content: str  # 记忆内容（如：用户的喜好、重要事实）
    memory_type: str  # 记忆类型（fact, preference, event 等）
    importance_score: float  # 重要性分数（0-1，越高越重要）
    created_at: str  # 创建时间


class UserProfileResponse(BaseModel):
    """
    用户画像响应模型
    
    表示基于对话历史生成的用户特征描述
    """
    persona_id: int
    interests: List[str]  # 兴趣爱好列表
    communication_style: str  # 沟通风格描述
    background_summary: str  # 背景摘要
    relationship_stage: str  # 关系阶段
    trust_level: float  # 信任度 0-1
    conversation_count: int  # 基于多少轮对话生成
    generated_at: str  # 生成时间
    updated_at: str  # 更新时间


class MemorySummaryResponse(BaseModel):
    """
    记忆摘要响应模型

    表示聚合后的记忆摘要
    """
    id: int
    summary_type: str  # 摘要类型
    title: str  # 摘要标题
    content: str  # 摘要内容
    key_points: List[str]  # 关键点列表
    memory_count: int  # 包含多少条记忆
    created_at: str  # 创建时间


class MessageResponse(BaseModel):
    """
    消息响应模型

    用于返回会话中的单条消息
    """
    id: int
    role: str  # "user" 或 "assistant"
    content: str  # 消息内容
    imageUrl: Optional[str] = None  # 表情包图片URL
    emojiInfo: Optional[dict] = None  # 表情包信息
    isEmoji: bool = False  # 是否为表情包消息
    timestamp: str  # 时间戳


class SessionHistoryResponse(BaseModel):
    """
    会话历史响应模型

    用于返回 Persona 的完整会话历史
    """
    session_id: int
    persona_id: int
    messages: List[MessageResponse]
    total: int


# ==================== 全局服务实例 ====================
# 这些全局变量在应用启动时初始化，在请求处理中使用

rag_service: Optional[RAGService] = None  # RAG 服务（表情包检索）
llm_service: Optional[LLMService] = None  # LLM 服务（对话生成）
persona_service = None  # 角色管理服务
memory_service = None  # 记忆服务
chroma_service = None  # ChromaDB 向量数据库服务
profile_service = None  # 用户画像服务
emoji_behavior_service = None  # 表情包行为分析服务
session_service = None  # 会话管理服务
dynamic_prompt_service = None  # 动态Prompt服务（新增）

# ==================== 持续学习配置 ====================
# 对话计数器：追踪每个Persona的对话轮数
conversation_counters: Dict[int, int] = {}
# 学习触发阈值：每N轮对话触发一次学习
LEARNING_INTERVAL = 10  # 可根据需要调整


# ==================== 应用生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    管理 FastAPI 应用的生命周期
    
    这是一个异步上下文管理器，在应用启动时执行初始化，
    在应用关闭时执行清理操作。
    
    初始化顺序：
    1. 数据库（SQLite）
    2. RAG 服务（FAISS + Sentence-Transformers）
    3. LLM 服务（OpenAI API / 豆包 API）
    4. 角色管理服务
    5. 记忆服务
    6. ChromaDB 向量数据库
    """
    global rag_service, llm_service, persona_service, memory_service, chroma_service, profile_service, emoji_behavior_service, session_service

    print("[启动] 正在初始化服务...")

    # 1. 初始化数据库
    try:
        from database import init_database
        init_database()
        print("[启动] 数据库初始化成功")
    except Exception as e:
        print(f"[启动] 数据库初始化失败: {e}")

    # 2. 初始化 RAG 服务（用于表情包检索）
    try:
        rag_service = RAGService(
            jsonl_path=os.path.join(PROJECT_ROOT, "emoji_classification.jsonl"),
            model_name="paraphrase-multilingual-MiniLM-L12-v2",  # 多语言嵌入模型
            embedding_dim=384  # 嵌入向量维度
        )
        rag_service.initialize()
        print("[启动] RAG 服务初始化成功")
    except Exception as e:
        print(f"[启动] RAG 服务初始化失败: {e}")
        rag_service = None

    # 3. 初始化 LLM 服务（用于对话生成）
    try:
        from dotenv import dotenv_values

        # 从 backend 目录的 .env 文件加载配置
        # 这样可以避免系统环境变量的干扰
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        env_config = dotenv_values(config_path)

        print(f"[启动] 正在读取配置: {config_path}")
        api_key = env_config.get("OPENAI_API_KEY", "")
        base_url = env_config.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = env_config.get("OPENAI_MODEL", "gpt-3.5-turbo")

        print(f"[启动] LLM 配置 - API Key: {api_key[:10]}...")
        print(f"[启动] LLM 配置 - Base URL: {base_url}")
        print(f"[启动] LLM 配置 - Model: {model}")

        llm_config = LLMConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.7,  # 创造性程度
            max_tokens=500  # 最大生成token数
        )
        llm_service = LLMService(llm_config)
        print("[启动] LLM 服务初始化成功")
    except Exception as e:
        print(f"[启动] LLM 服务初始化失败: {type(e).__name__}: {e}")
        import traceback
        print(f"[启动] LLM 初始化错误详情: {traceback.format_exc()}")
        llm_service = None
    
    # 4. 初始化角色管理服务
    try:
        from persona_service import get_persona_service
        persona_service = get_persona_service()
        print("[启动] 角色管理服务初始化成功")
    except Exception as e:
        print(f"[启动] 角色管理服务初始化失败: {e}")
        persona_service = None
    
    # 5. 初始化记忆服务
    try:
        from memory_service import get_memory_service
        memory_service = get_memory_service()
        print("[Startup] Memory service initialized successfully")
    except Exception as e:
        print(f"[Startup] Error initializing memory service: {e}")
        memory_service = None
    
    # 6. 初始化 ChromaDB 向量数据库服务
    # 注意：ChromaDB 初始化可能会加载嵌入模型，耗时较长
    # 如果初始化失败，系统会回退到 SQLite 存储
    chroma_service = None  # 默认设为 None，避免阻塞
    try:
        from chroma_service import get_chroma_service
        # 使用延迟初始化，避免在启动时阻塞
        # ChromaDB 会在第一次使用时自动初始化
        chroma_service = get_chroma_service()
        print("[启动] ChromaDB 服务初始化成功")
    except Exception as e:
        print(f"[启动] ChromaDB 服务初始化失败: {e}")
        print("[启动] 将使用 SQLite 作为对话存储的备选方案")
        chroma_service = None
    
    # 7. 初始化用户画像服务
    try:
        from user_profile_service import get_user_profile_service
        profile_service = get_user_profile_service(llm_service=llm_service)
        print("[启动] 用户画像服务初始化成功")
    except Exception as e:
        print(f"[启动] 用户画像服务初始化失败: {e}")
        profile_service = None

    # 8. 初始化表情包行为分析服务
    try:
        if EMOJI_BEHAVIOR_AVAILABLE:
            emoji_behavior_service = get_emoji_behavior_service()
            print("[启动] 表情包行为分析服务初始化成功")
        else:
            emoji_behavior_service = None
    except Exception as e:
        print(f"[启动] 表情包行为分析服务初始化失败: {e}")
        emoji_behavior_service = None

    # 9. 初始化会话管理服务
    try:
        if SESSION_SERVICE_AVAILABLE:
            session_service = get_session_service()
            print("[启动] 会话管理服务初始化成功")
        else:
            session_service = None
    except Exception as e:
        print(f"[启动] 会话管理服务初始化失败: {e}")
        session_service = None

    print("[启动] 所有服务初始化完成！")

    yield

    # Shutdown
    print("[Shutdown] Cleaning up resources...")
    rag_service = None
    llm_service = None
    persona_service = None
    memory_service = None
    chroma_service = None
    profile_service = None
    emoji_behavior_service = None
    session_service = None
    print("[Shutdown] Cleanup complete")


# ==================== FastAPI Application ====================

app = FastAPI(
    title="Digital Twin Chatbot API",
    description="基于 RAG 的数字孪生对话智能体后端 API",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for emoji images
app.mount("/static/emojis", StaticFiles(directory=os.path.join(PROJECT_ROOT, "emojis")), name="emoji_images")


# ==================== API Endpoints ====================

@app.get("/", response_model=dict)
async def root():
    """Root endpoint - API information."""
    return {
        "name": "Digital Twin Chatbot API",
        "version": "2.0.0",
        "docs_url": "/docs",
        "health_url": "/api/health",
        "features": [
            "Digital Twin Persona Management",
            "Chat History Import",
            "Memory System",
            "RAG-based Emoji Retrieval",
            "Personalized Responses"
        ]
    }


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    rag_stats = rag_service.get_stats() if rag_service else {"initialized": False}
    llm_stats = llm_service.check_health() if llm_service else {"configured": False}
    static_files_ok = os.path.exists(os.path.join(PROJECT_ROOT, "emojis"))
    
    # Check database
    db_status = {"initialized": False}
    try:
        from database import get_db
        from sqlalchemy import text
        db = get_db()
        db.execute(text("SELECT 1"))
        db_status = {"initialized": True}
    except Exception as e:
        db_status = {"initialized": False, "error": str(e)}
    
    # Check ChromaDB
    chroma_stats = {"initialized": False}
    try:
        from chroma_service import get_chroma_service
        cs = get_chroma_service()
        chroma_stats = cs.get_stats()
    except Exception as e:
        chroma_stats = {"initialized": False, "error": str(e)}

    return HealthResponse(
        status="healthy" if (rag_service and llm_service and db_status["initialized"]) else "degraded",
        rag_service=rag_stats,
        llm_service=llm_stats,
        static_files={"exists": static_files_ok, "path": "./emojis"},
        database=db_status,
        chromadb=chroma_stats
    )


# ==================== Persona Management Endpoints ====================

@app.get("/api/personas", response_model=List[PersonaResponse])
async def list_personas():
    """List all available personas."""
    if not persona_service:
        raise HTTPException(status_code=503, detail="Persona service not initialized")

    try:
        personas = persona_service.list_personas()
        return [
            PersonaResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                avatar_url=p.avatar_url,
                personality_traits=p.personality_traits or {},
                common_phrases=p.common_phrases or [],
                emoji_preferences=p.emoji_preferences or [],
                emoji_usage_frequency=p.emoji_usage_frequency or "medium",
                emoji_usage_rate=p.emoji_usage_rate or 0.5,
                emoji_scenario_prefs=p.emoji_scenario_prefs or [],
                emoji_type_prefs=p.emoji_type_prefs or [],
                avg_response_length=p.avg_response_length or 50,
                response_style=p.response_style or "casual",
                created_at=p.created_at.isoformat() if p.created_at else None,
                updated_at=p.updated_at.isoformat() if p.updated_at else None
            )
            for p in personas
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing personas: {str(e)}")


@app.post("/api/personas", response_model=PersonaResponse)
async def create_persona(request: PersonaCreateRequest):
    """Create a new digital twin persona."""
    if not persona_service:
        raise HTTPException(status_code=503, detail="Persona service not initialized")

    try:
        persona = persona_service.create_persona(
            name=request.name,
            description=request.description,
            avatar_url=request.avatar_url
        )
        return PersonaResponse(
            id=persona.id,
            name=persona.name,
            description=persona.description,
            avatar_url=persona.avatar_url,
            personality_traits=persona.personality_traits or {},
            common_phrases=persona.common_phrases or [],
            emoji_preferences=persona.emoji_preferences or [],
            emoji_usage_frequency=persona.emoji_usage_frequency or "medium",
            emoji_usage_rate=persona.emoji_usage_rate or 0.5,
            emoji_scenario_prefs=persona.emoji_scenario_prefs or [],
            emoji_type_prefs=persona.emoji_type_prefs or [],
            avg_response_length=persona.avg_response_length or 50,
            response_style=persona.response_style or "casual",
            created_at=persona.created_at.isoformat() if persona.created_at else None,
            updated_at=persona.updated_at.isoformat() if persona.updated_at else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating persona: {str(e)}")


@app.get("/api/personas/{persona_id}", response_model=PersonaResponse)
async def get_persona(persona_id: int):
    """Get a specific persona by ID."""
    if not persona_service:
        raise HTTPException(status_code=503, detail="Persona service not initialized")

    try:
        persona = persona_service.get_persona(persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

        return PersonaResponse(
            id=persona.id,
            name=persona.name,
            description=persona.description,
            avatar_url=persona.avatar_url,
            personality_traits=persona.personality_traits or {},
            common_phrases=persona.common_phrases or [],
            emoji_preferences=persona.emoji_preferences or [],
            emoji_usage_frequency=persona.emoji_usage_frequency or "medium",
            emoji_usage_rate=persona.emoji_usage_rate or 0.5,
            emoji_scenario_prefs=persona.emoji_scenario_prefs or [],
            emoji_type_prefs=persona.emoji_type_prefs or [],
            avg_response_length=persona.avg_response_length or 50,
            response_style=persona.response_style or "casual",
            created_at=persona.created_at.isoformat() if persona.created_at else None,
            updated_at=persona.updated_at.isoformat() if persona.updated_at else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting persona: {str(e)}")


@app.post("/api/personas/{persona_id}/import", response_model=ImportChatHistoryResponse)
async def import_chat_history(
    persona_id: int,
    file: UploadFile = File(...),
    persona_identifier: Optional[str] = Form(None)
):
    """Import chat history from a WeChat export file for a persona."""
    if not persona_service:
        raise HTTPException(status_code=503, detail="Persona service not initialized")
    
    try:
        # Save uploaded file temporarily
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Import chat history
        result = persona_service.import_chat_history(
            persona_id=persona_id,
            file_path=temp_path,
            persona_identifier=persona_identifier
        )
        
        # Clean up temp file
        os.remove(temp_path)
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])

        # 导入成功后，自动分析表情包行为
        if emoji_behavior_service:
            try:
                emoji_result = emoji_behavior_service.analyze_and_update_persona(persona_id)
                print(f"[Import] Emoji behavior analyzed: {emoji_result.get('emoji_usage_frequency', 'unknown')}")
            except Exception as e:
                print(f"[Import] Error analyzing emoji behavior: {e}")

        return ImportChatHistoryResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing chat history: {str(e)}")


@app.post("/api/personas/{persona_id}/analyze-emoji-behavior")
async def analyze_emoji_behavior(persona_id: int):
    """
    分析用户的表情包使用行为

    从聊天记录中学习用户的表情包使用习惯：
    - 使用频率（高频/中频/低频/不使用）
    - 使用场景偏好
    - 表情包类型偏好

    核心理念：尊重用户习惯，不强行推荐表情包给不使用的用户
    """
    if not emoji_behavior_service:
        raise HTTPException(status_code=503, detail="Emoji behavior service not initialized")

    try:
        result = emoji_behavior_service.analyze_and_update_persona(persona_id)
        return {
            "status": "success",
            "persona_id": persona_id,
            "emoji_behavior": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing emoji behavior: {str(e)}")


@app.get("/api/personas/{persona_id}/emoji-behavior")
async def get_emoji_behavior(persona_id: int):
    """
    获取用户的表情包行为画像

    返回用户的表情包使用习惯信息
    """
    if not persona_service:
        raise HTTPException(status_code=503, detail="Persona service not initialized")

    try:
        persona = persona_service.get_persona(persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

        return {
            "persona_id": persona_id,
            "emoji_usage_frequency": persona.emoji_usage_frequency or "medium",
            "emoji_usage_rate": persona.emoji_usage_rate or 0.5,
            "emoji_scenario_prefs": persona.emoji_scenario_prefs or [],
            "emoji_type_prefs": persona.emoji_type_prefs or [],
            "should_use_emoji": emoji_behavior_service.should_recommend_emoji(persona_id) if emoji_behavior_service else True
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting emoji behavior: {str(e)}")


# ==================== Personalized Chat Endpoints ====================

@app.post("/api/chat/personalized", response_model=PersonalizedChatResponse)
async def chat_personalized(request: PersonalizedChatRequest):
    """
    Chat with a digital twin persona.
    
    This endpoint generates personalized responses that mimic
    the speaking style of the specified persona.
    """
    if not rag_service or not llm_service or not persona_service:
        raise HTTPException(
            status_code=503,
            detail="Services not initialized. Please check /api/health"
        )

    try:
        import time
        start_time = time.time()

        # Verify persona exists
        persona = persona_service.get_persona(request.persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

        # 获取或创建会话（用于消息持久化）
        current_session_id = None
        if session_service:
            try:
                session = session_service.get_or_create_session(request.persona_id)
                current_session_id = session.id
            except Exception as e:
                print(f"[Chat] Error getting session: {e}")

        # Convert history to format expected by LLM service
        history = None
        if request.history:
            history = [{"role": msg.role, "content": msg.content} for msg in request.history]

        # 处理用户发送表情包的情况
        user_message = request.message
        user_sent_emoji = False
        emoji_boost = 0.0  # 表情包触发概率提升

        if request.user_emoji_url:
            user_sent_emoji = True
            emoji_boost = 0.3  # 用户发表情包时，提高对方回复表情包的概率30%

            # 构建包含表情包描述的消息
            emoji_desc = request.user_emoji_description or "一个表情包"
            if user_message:
                user_message = f"{user_message} [发送了表情包：{emoji_desc}]"
            else:
                user_message = f"[发送了一个表情包：{emoji_desc}]"

        # Analyze intent with persona context
        intent = llm_service.analyze_intent(
            user_message=user_message,
            conversation_history=history,
            persona_id=request.persona_id,
            user_sent_emoji=user_sent_emoji  # 传递用户是否发送表情包的标志
        )

        retrieved_emoji = None
        image_url = None

        # 如果用户发送了表情包，提高助手回复表情包的概率
        needs_emoji = intent.needs_emoji
        if user_sent_emoji and not needs_emoji:
            # 用户发表情包时，有概率也回复表情包
            import random
            if random.random() < (0.4 + emoji_boost):  # 基础40% + 提升30% = 70%
                needs_emoji = True
                # 使用用户表情包的描述作为搜索关键词
                if request.user_emoji_description:
                    intent.search_query = request.user_emoji_description

        # Search for emoji if intent requires it
        if needs_emoji and intent.search_query:
            results = rag_service.search(
                query=intent.search_query,
                top_k=1,
                score_threshold=0.25  # 稍微降低阈值
            )

            if results:
                retrieved_emoji = results[0]
                file_name = retrieved_emoji.get('file_name', '')
                image_url = f"/static/emojis/{file_name}"

        # Generate personalized response
        chat_response = llm_service.generate_personalized_response(
            user_message=user_message,
            persona_id=request.persona_id,
            session_id=request.session_id,
            retrieved_emoji=retrieved_emoji,
            conversation_history=history,
            use_memory=request.use_memory,
            stream=False,
            user_sent_emoji=user_sent_emoji  # 传递给LLM服务
        )

        # 保存消息到数据库
        if session_service and current_session_id:
            try:
                # 保存用户消息
                user_emoji_url = request.user_emoji_url
                user_emoji_desc = request.user_emoji_description

                session_service.add_message(
                    session_id=current_session_id,
                    role="user",
                    content=request.message or "",
                    emoji_url=user_emoji_url,
                    emoji_description=user_emoji_desc
                )

                # 保存助手回复
                assistant_emoji_url = image_url
                assistant_emoji_desc = None
                if retrieved_emoji:
                    assistant_emoji_desc = retrieved_emoji.get("description")

                session_service.add_message(
                    session_id=current_session_id,
                    role="assistant",
                    content=chat_response,
                    emoji_url=assistant_emoji_url,
                    emoji_description=assistant_emoji_desc
                )
            except Exception as e:
                print(f"[Chat] Error saving messages: {e}")

        # Extract memories from conversation if memory is enabled
        if request.use_memory and memory_service:
            try:
                memory_service.extract_memories_from_message(
                    persona_id=request.persona_id,
                    user_message=request.message,
                    assistant_response=chat_response,
                    session_id=request.session_id
                )
            except Exception as e:
                print(f"[Chat] Error extracting memories: {e}")

        # Auto-update user profile if needed
        if request.use_memory and profile_service:
            try:
                updated = profile_service.auto_update_if_needed(request.persona_id)
                if updated:
                    print(f"[Chat] User profile updated for persona {request.persona_id}")
            except Exception as e:
                print(f"[Chat] Error updating user profile: {e}")

        # ===== 持续学习自动触发 =====
        # 每 LEARNING_INTERVAL 轮对话自动触发一次学习
        if DYNAMIC_PROMPT_AVAILABLE:
            try:
                triggered = trigger_learning_if_needed(request.persona_id)
                if triggered:
                    print(f"[Chat] Continuous learning triggered for persona {request.persona_id}")
            except Exception as e:
                print(f"[Chat] Error triggering learning: {e}")
        
        elapsed = time.time() - start_time
        print(f"[Chat Personalized] Processed in {elapsed:.2f}s")
        
        # Build response
        response_data = {
            "text": chat_response,
            "image_url": image_url,
            "emoji_info": None,
            "persona_id": request.persona_id,
            "session_id": current_session_id,  # 返回实际的 session_id
            "memory_used": request.use_memory
        }
        
        if retrieved_emoji:
            response_data["emoji_info"] = {
                "description": retrieved_emoji.get("description", ""),
                "sub_category": retrieved_emoji.get("sub_category", ""),
                "score": retrieved_emoji.get("score", 0)
            }
        
        return PersonalizedChatResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Chat Personalized] Error processing request: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat request: {str(e)}"
        )


# ==================== Session Endpoints ====================

@app.get("/api/personas/{persona_id}/session", response_model=SessionHistoryResponse)
async def get_persona_session(persona_id: int):
    """
    获取 Persona 的会话历史

    返回该 Persona 的所有历史消息，用于前端加载
    """
    if not session_service:
        raise HTTPException(status_code=503, detail="Session service not initialized")

    try:
        # 确保 Persona 存在
        if persona_service:
            persona = persona_service.get_persona(persona_id)
            if not persona:
                raise HTTPException(status_code=404, detail="Persona not found")

        # 获取或创建会话
        session = session_service.get_or_create_session(persona_id)
        messages = session_service.get_session_messages(session.id)

        return SessionHistoryResponse(
            session_id=session.id,
            persona_id=persona_id,
            messages=[
                MessageResponse(
                    id=msg.id,
                    role=msg.role,
                    content=msg.content,
                    imageUrl=msg.emoji_url,
                    emojiInfo={"description": msg.emoji_description} if msg.emoji_description else None,
                    isEmoji=msg.emoji_url is not None,  # 有表情包URL则为True
                    timestamp=msg.created_at.isoformat() if msg.created_at else None
                )
                for msg in messages
            ],
            total=len(messages)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting session: {str(e)}")


# ==================== Learning Endpoints ====================

class LearningStatusResponse(BaseModel):
    """学习状态响应模型"""
    persona_id: int
    conversation_count: int
    learning_interval: int
    next_learning_at: int
    last_learning_result: Optional[Dict[str, Any]] = None


class LearningTriggerResponse(BaseModel):
    """学习触发响应模型"""
    persona_id: int
    triggered: bool
    message: str
    updates: Optional[Dict[str, Any]] = None


@app.get("/api/personas/{persona_id}/learning/status", response_model=LearningStatusResponse)
async def get_learning_status(persona_id: int):
    """
    获取持续学习状态

    返回当前对话计数、学习间隔等信息
    """
    count = conversation_counters.get(persona_id, 0)

    return LearningStatusResponse(
        persona_id=persona_id,
        conversation_count=count,
        learning_interval=LEARNING_INTERVAL,
        next_learning_at=LEARNING_INTERVAL - (count % LEARNING_INTERVAL)
    )


@app.post("/api/personas/{persona_id}/learning/trigger", response_model=LearningTriggerResponse)
async def trigger_manual_learning(persona_id: int):
    """
    手动触发持续学习

    立即执行学习任务，更新Persona特征
    """
    if not DYNAMIC_PROMPT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Dynamic prompt service not available")

    try:
        # 确保 Persona 存在
        if persona_service:
            persona = persona_service.get_persona(persona_id)
            if not persona:
                raise HTTPException(status_code=404, detail="Persona not found")

        # 执行学习
        dynamic_svc = get_dynamic_prompt_service()
        result = dynamic_svc.learn_and_update(persona_id)

        if result and 'updates' in result and result['updates']:
            return LearningTriggerResponse(
                persona_id=persona_id,
                triggered=True,
                message="Learning completed with updates",
                updates=result['updates']
            )
        else:
            return LearningTriggerResponse(
                persona_id=persona_id,
                triggered=True,
                message="Learning completed, no updates needed",
                updates=None
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in learning: {str(e)}")


@app.post("/api/personas/{persona_id}/learning/reset")
async def reset_learning_counter(persona_id: int):
    """
    重置对话计数器

    用于测试或重新开始计数
    """
    global conversation_counters
    conversation_counters[persona_id] = 0

    return {
        "persona_id": persona_id,
        "message": "Learning counter reset",
        "new_count": 0
    }


# ==================== Memory Endpoints ====================

@app.get("/api/personas/{persona_id}/memories", response_model=List[MemoryResponse])
async def get_memories(persona_id: int, memory_type: Optional[str] = None):
    """Get memories for a persona."""
    if not memory_service:
        raise HTTPException(status_code=503, detail="Memory service not initialized")
    
    try:
        memories = memory_service.get_memories(persona_id, memory_type=memory_type)
        return [
            MemoryResponse(
                id=m.id,
                content=m.content,
                memory_type=m.memory_type,
                importance_score=m.importance_score,
                created_at=m.created_at.isoformat() if m.created_at else None
            )
            for m in memories
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting memories: {str(e)}")


@app.get("/api/personas/{persona_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(persona_id: int):
    """
    获取用户画像
    
    基于对话历史生成的用户特征描述
    """
    if not profile_service:
        raise HTTPException(status_code=503, detail="Profile service not initialized")
    
    try:
        profile = profile_service.get_or_create_user_profile(persona_id)
        
        # 解析JSON字段
        import json
        interests = []
        if profile.interests:
            try:
                interests = json.loads(profile.interests)
            except:
                interests = []
        
        return UserProfileResponse(
            persona_id=profile.persona_id,
            interests=interests,
            communication_style=profile.communication_style or "",
            background_summary=profile.background_summary or "",
            relationship_stage=profile.relationship_stage,
            trust_level=profile.trust_level,
            conversation_count=profile.conversation_count,
            generated_at=profile.generated_at.isoformat() if profile.generated_at else None,
            updated_at=profile.updated_at.isoformat() if profile.updated_at else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user profile: {str(e)}")


@app.post("/api/personas/{persona_id}/profile/generate")
async def generate_user_profile(persona_id: int):
    """
    手动触发用户画像生成
    
    基于当前所有记忆重新生成用户画像
    """
    if not profile_service:
        raise HTTPException(status_code=503, detail="Profile service not initialized")
    
    try:
        profile = profile_service.generate_user_profile(persona_id, force_update=True)
        
        # 同时生成记忆摘要
        summaries = []
        for summary_type in ["preference", "fact", "event"]:
            summary = profile_service.generate_memory_summary(persona_id, summary_type)
            if summary:
                summaries.append(summary_type)
        
        return {
            "status": "success",
            "message": f"User profile generated for persona {persona_id}",
            "conversation_count": profile.conversation_count,
            "summaries_generated": summaries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating user profile: {str(e)}")


@app.get("/api/personas/{persona_id}/summaries", response_model=List[MemorySummaryResponse])
async def get_memory_summaries(persona_id: int, summary_type: Optional[str] = None):
    """
    获取记忆摘要
    
    获取聚合后的记忆摘要列表
    """
    if not profile_service:
        raise HTTPException(status_code=503, detail="Profile service not initialized")
    
    try:
        from database import MemorySummary
        
        query = profile_service.db.query(MemorySummary).filter(
            MemorySummary.persona_id == persona_id
        )
        
        if summary_type:
            query = query.filter(MemorySummary.summary_type == summary_type)
        
        summaries = query.order_by(MemorySummary.created_at.desc()).all()
        
        import json
        result = []
        for s in summaries:
            key_points = []
            if s.key_points:
                try:
                    key_points = json.loads(s.key_points)
                except:
                    key_points = []
            
            result.append(MemorySummaryResponse(
                id=s.id,
                summary_type=s.summary_type,
                title=s.title,
                content=s.content,
                key_points=key_points,
                memory_count=s.memory_count,
                created_at=s.created_at.isoformat() if s.created_at else None
            ))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting memory summaries: {str(e)}")


# ==================== Advanced Memory System Endpoints ====================

class JournalResponse(BaseModel):
    """Timeline journal response model."""
    id: int
    journal_type: str
    date: str
    summary: str
    key_events: List[Dict[str, Any]] = []
    preference_changes: List[Dict[str, Any]] = []
    mood_trend: str
    message_count: int
    topics_discussed: List[str] = []
    created_at: Optional[str] = None


class HotMemoryResponse(BaseModel):
    """Hot memory response model."""
    id: int
    content: str
    memory_type: str
    access_frequency: int
    created_at: Optional[str] = None


class MemoryConflictResponse(BaseModel):
    """Memory conflict detection response."""
    has_conflict: bool
    conflicts: List[Dict[str, Any]] = []
    action_taken: Optional[Dict[str, Any]] = None


@app.post("/api/personas/{persona_id}/journal/generate")
async def generate_journal(persona_id: int, date: Optional[str] = None):
    """
    手动生成日记

    为指定日期生成每日日记。如果未指定日期，则生成今天的日记。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        advanced_memory = get_advanced_memory_service()

        # 解析日期
        journal_date = None
        if date:
            try:
                journal_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        journal = advanced_memory.generate_daily_journal(persona_id, journal_date)

        if not journal:
            return {
                "status": "no_data",
                "message": f"No messages found for the specified date"
            }

        return {
            "status": "success",
            "journal": {
                "id": journal.id,
                "journal_type": journal.journal_type,
                "date": journal.date.isoformat() if journal.date else None,
                "summary": journal.summary,
                "message_count": journal.message_count,
                "mood_trend": journal.mood_trend
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating journal: {str(e)}")


@app.post("/api/personas/{persona_id}/journal/generate-weekly")
async def generate_weekly_journal(persona_id: int, week_start: Optional[str] = None):
    """
    手动生成周记

    为指定周生成周记。如果未指定周起始日期，则生成本周的周记。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        advanced_memory = get_advanced_memory_service()

        # 解析周起始日期
        week_start_date = None
        if week_start:
            try:
                week_start_date = datetime.strptime(week_start, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        journal = advanced_memory.generate_weekly_journal(persona_id, week_start_date)

        if not journal:
            return {
                "status": "no_data",
                "message": "No daily journals found for the specified week"
            }

        return {
            "status": "success",
            "journal": {
                "id": journal.id,
                "journal_type": journal.journal_type,
                "date": journal.date.isoformat() if journal.date else None,
                "summary": journal.summary,
                "message_count": journal.message_count,
                "mood_trend": journal.mood_trend
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating weekly journal: {str(e)}")


@app.get("/api/personas/{persona_id}/journals", response_model=List[JournalResponse])
async def get_journals(persona_id: int, days: int = 30, journal_type: Optional[str] = None):
    """
    获取日记列表

    获取最近N天的日记。可以通过 journal_type 参数筛选 daily 或 weekly。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        advanced_memory = get_advanced_memory_service()
        journals = advanced_memory.get_recent_journals(persona_id, days=days)

        # 按类型筛选
        if journal_type:
            journals = [j for j in journals if j.journal_type == journal_type]

        return [
            JournalResponse(
                id=j.id,
                journal_type=j.journal_type,
                date=j.date.isoformat() if j.date else "",
                summary=j.summary or "",
                key_events=j.key_events or [],
                preference_changes=j.preference_changes or [],
                mood_trend=j.mood_trend or "neutral",
                message_count=j.message_count,
                topics_discussed=j.topics_discussed or [],
                created_at=j.created_at.isoformat() if j.created_at else None
            )
            for j in journals
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting journals: {str(e)}")


@app.get("/api/personas/{persona_id}/hot-memories", response_model=List[HotMemoryResponse])
async def get_hot_memories(persona_id: int):
    """
    获取热记忆列表

    热记忆是高频访问的记忆，直接注入System Prompt以减少向量检索开销。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        from database import HotMemory

        advanced_memory = get_advanced_memory_service()
        db = advanced_memory.db

        hot_memories = db.query(HotMemory).filter(
            HotMemory.persona_id == persona_id
        ).order_by(HotMemory.access_frequency.desc()).limit(10).all()

        return [
            HotMemoryResponse(
                id=hm.id,
                content=hm.content,
                memory_type=hm.memory_type,
                access_frequency=hm.access_frequency,
                created_at=hm.created_at.isoformat() if hm.created_at else None
            )
            for hm in hot_memories
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting hot memories: {str(e)}")


@app.post("/api/personas/{persona_id}/memories/{memory_id}/promote")
async def promote_to_hot_memory(persona_id: int, memory_id: int):
    """
    将记忆提升为热记忆

    将指定记忆标记为热记忆，使其直接注入System Prompt。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        advanced_memory = get_advanced_memory_service()
        hot_memory = advanced_memory.promote_to_hot_memory(memory_id)

        if not hot_memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        return {
            "status": "success",
            "hot_memory": {
                "id": hot_memory.id,
                "content": hot_memory.content,
                "memory_type": hot_memory.memory_type,
                "access_frequency": hot_memory.access_frequency
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error promoting memory: {str(e)}")


@app.post("/api/personas/{persona_id}/memories/{memory_id}/update")
async def update_memory(memory_id: int, persona_id: int, new_content: str, reason: str = ""):
    """
    更新记忆（带版本追踪）

    更新记忆内容并创建版本记录，支持记忆的可变性追踪。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        advanced_memory = get_advanced_memory_service()
        updated_memory = advanced_memory.update_memory(memory_id, new_content, reason)

        if not updated_memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        return {
            "status": "success",
            "memory": {
                "id": updated_memory.id,
                "content": updated_memory.content,
                "updated_at": updated_memory.last_accessed.isoformat() if updated_memory.last_accessed else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating memory: {str(e)}")


@app.post("/api/personas/{persona_id}/memories/check-conflict", response_model=MemoryConflictResponse)
async def check_memory_conflict(persona_id: int, new_content: str, async_mode: bool = True):
    """
    检测记忆冲突

    检查新记忆内容是否与现有记忆存在冲突，并自动解决冲突。

    Args:
        async_mode: 如果为True，立即返回并在后台处理冲突；
                   如果为False，同步等待结果（可能较慢）
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        if async_mode:
            # 异步模式：立即返回，后台处理
            trigger_memory_consolidation(persona_id, new_content)

            return MemoryConflictResponse(
                has_conflict=False,  # 尚未检测
                conflicts=[],
                action_taken={"type": "async_scheduled", "message": "Conflict detection scheduled in background"}
            )
        else:
            # 同步模式：等待结果
            advanced_memory = get_advanced_memory_service()
            result = advanced_memory.detect_and_resolve_conflict(persona_id, new_content)

            return MemoryConflictResponse(
                has_conflict=result.get("has_conflict", False),
                conflicts=result.get("conflicts", []),
                action_taken=result.get("action_taken")
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking conflict: {str(e)}")


@app.post("/api/personas/{persona_id}/memories/merge")
async def merge_similar_memories(persona_id: int, threshold: float = 0.9, async_mode: bool = True):
    """
    合并相似记忆

    自动检测并合并相似度超过阈值的记忆，减少冗余。

    Args:
        async_mode: 如果为True，立即返回并在后台处理；
                   如果为False，同步等待结果
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        if async_mode:
            # 异步模式：立即返回，后台处理
            trigger_memory_consolidation(persona_id)

            return {
                "status": "scheduled",
                "merged_count": 0,
                "message": "Memory merge scheduled in background"
            }
        else:
            # 同步模式：等待结果
            advanced_memory = get_advanced_memory_service()
            merged_count = advanced_memory.merge_similar_memories(persona_id, threshold)

            return {
                "status": "success",
                "merged_count": merged_count,
                "message": f"Merged {merged_count} similar memories"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error merging memories: {str(e)}")


@app.get("/api/personas/{persona_id}/memory-context")
async def get_memory_context(
    persona_id: int,
    session_id: Optional[int] = None,
    user_message: str = ""
):
    """
    获取完整记忆上下文（三层架构）

    返回所有三层记忆的内容，用于调试和展示。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        advanced_memory = get_advanced_memory_service()
        contexts = advanced_memory.get_all_memory_context(
            persona_id=persona_id,
            session_id=session_id,
            user_message=user_message
        )

        return {
            "persona_id": persona_id,
            "hot_memory": contexts.get("hot_memory", ""),
            "scratchpad": contexts.get("scratchpad", ""),
            "journals": contexts.get("journals", ""),
            "cold_memory": contexts.get("cold_memory", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting memory context: {str(e)}")


@app.post("/api/personas/{persona_id}/scratchpad/update")
async def update_scratchpad(
    persona_id: int,
    session_id: int,
    key: str,
    value: Any
):
    """
    更新临时工作区

    更新当前会话的临时工作区（Scratchpad）。
    """
    if not ADVANCED_MEMORY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Advanced memory service not available")

    try:
        advanced_memory = get_advanced_memory_service()
        scratchpad = advanced_memory.update_scratchpad(session_id, persona_id, key, value)

        return {
            "status": "success",
            "scratchpad": {
                "id": scratchpad.id,
                "current_task": scratchpad.current_task,
                "emotional_state": scratchpad.emotional_state,
                "active_topics": scratchpad.active_topics
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating scratchpad: {str(e)}")


# ==================== Legacy Chat Endpoints ====================

class FastChatResponse(BaseModel):
    """Fast chat response model."""
    text: str = Field(..., description="Assistant's text response")
    image_url: Optional[str] = Field(default=None, description="URL to the recommended emoji image")
    emoji_info: Optional[dict] = Field(default=None, description="Information about the retrieved emoji")
    used_fallback: bool = Field(default=False, description="Whether fallback mode was used")


@app.post("/api/chat/fast", response_model=FastChatResponse)
async def chat_fast(request: ChatRequest):
    """
    Fast chat endpoint with single LLM call.
    Combines intent analysis and response generation for better performance.
    """
    if not rag_service or not llm_service:
        raise HTTPException(
            status_code=503,
            detail="Services not initialized. Please check /api/health"
        )

    try:
        import time
        start_time = time.time()

        # Convert history to format expected by LLM service
        history = None
        if request.history:
            history = [{"role": msg.role, "content": msg.content} for msg in request.history]

        # Use combined approach: analyze intent and get search query in one call
        intent = llm_service.analyze_intent(
            user_message=request.message,
            conversation_history=history
        )

        retrieved_emoji = None
        image_url = None

        # Search for emoji if intent requires it
        if intent.needs_emoji and intent.search_query:
            results = rag_service.search(
                query=intent.search_query,
                top_k=1,
                score_threshold=0.3
            )

            if results:
                retrieved_emoji = results[0]
                file_name = retrieved_emoji.get('file_name', '')
                image_url = f"/static/emojis/{file_name}"

        # Generate chat response
        chat_response = llm_service.generate_chat_response(
            user_message=request.message,
            retrieved_emoji=retrieved_emoji,
            conversation_history=history
        )

        elapsed = time.time() - start_time
        print(f"[Chat Fast] Processed in {elapsed:.2f}s")

        # Build response
        response_data = {
            "text": chat_response,
            "image_url": image_url,
            "emoji_info": None,
            "used_fallback": "Fallback" in intent.reasoning
        }

        if retrieved_emoji:
            response_data["emoji_info"] = {
                "description": retrieved_emoji.get("description", ""),
                "sub_category": retrieved_emoji.get("sub_category", ""),
                "score": retrieved_emoji.get("score", 0)
            }

        return FastChatResponse(**response_data)

    except Exception as e:
        print(f"[Chat Fast] Error processing request: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat request: {str(e)}"
        )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint with RAG-based emoji retrieval (legacy, use /api/chat/fast for better performance)."""
    if not rag_service or not llm_service:
        raise HTTPException(
            status_code=503,
            detail="Services not initialized. Please check /api/health"
        )

    try:
        # Convert history to format expected by LLM service
        history = None
        if request.history:
            history = [{"role": msg.role, "content": msg.content} for msg in request.history]

        # Step 1: Analyze intent using LLM
        intent = llm_service.analyze_intent(
            user_message=request.message,
            conversation_history=history
        )

        retrieved_emoji = None
        image_url = None

        # Step 2: Search for emoji if intent requires it
        if intent.needs_emoji and intent.search_query:
            results = rag_service.search(
                query=intent.search_query,
                top_k=1,
                score_threshold=0.4
            )

            if results:
                retrieved_emoji = results[0]
                file_name = retrieved_emoji.get('file_name', '')
                image_url = f"/static/emojis/{file_name}"

        # Step 3: Generate chat response
        chat_response = llm_service.generate_chat_response(
            user_message=request.message,
            retrieved_emoji=retrieved_emoji,
            conversation_history=history
        )

        # Build response
        response_data = {
            "text": chat_response,
            "image_url": image_url,
            "emoji_info": None
        }

        if retrieved_emoji:
            response_data["emoji_info"] = {
                "description": retrieved_emoji.get("description", ""),
                "sub_category": retrieved_emoji.get("sub_category", ""),
                "score": retrieved_emoji.get("score", 0)
            }

        return ChatResponse(**response_data)

    except Exception as e:
        print(f"[Chat] Error processing request: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat request: {str(e)}"
        )


@app.get("/api/search", response_model=SearchResponse)
async def search_emojis(q: str, top_k: int = 5):
    """Direct emoji search endpoint."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    try:
        results = rag_service.search(
            query=q,
            top_k=top_k,
            score_threshold=0.2
        )

        for result in results:
            file_name = result.get('file_name', '')
            result['image_url'] = f"/static/emojis/{file_name}"

        return SearchResponse(query=q, results=results, total=len(results))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.get("/api/emojis/random")
async def random_emoji():
    """Get a random emoji from the database."""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    emoji = rag_service.get_random_emoji()
    if not emoji:
        raise HTTPException(status_code=404, detail="No emojis available")

    file_name = emoji.get('file_name', '')
    emoji['image_url'] = f"/static/emojis/{file_name}"

    return emoji


class EmojiRecommendRequest(BaseModel):
    """表情包推荐请求"""
    text: str = Field(..., description="用户输入的文字")
    top_k: int = Field(default=8, description="返回结果数量")


class EmojiRecommendResponse(BaseModel):
    """表情包推荐响应"""
    results: List[dict] = Field(default=[], description="推荐的表情包列表")


@app.post("/api/emoji/recommend", response_model=EmojiRecommendResponse)
async def recommend_emoji(request: EmojiRecommendRequest):
    """
    根据用户输入的文字推荐表情包

    用于用户选择发送表情包的场景
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    try:
        # 使用RAG服务搜索相关表情包
        results = rag_service.search(
            query=request.text,
            top_k=request.top_k,
            score_threshold=0.15  # 降低阈值以获得更多结果
        )

        # 添加图片URL
        for result in results:
            file_name = result.get('file_name', '')
            result['image_url'] = f"/static/emojis/{file_name}"

        return EmojiRecommendResponse(results=results)

    except Exception as e:
        print(f"[Emoji Recommend] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Recommend error: {str(e)}")


@app.get("/api/emoji/{emoji_md5}")
async def get_emoji_info(emoji_md5: str):
    """
    获取表情包信息

    通过MD5获取表情包的详细信息
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    try:
        # 从RAG服务获取表情包信息
        emoji_info = rag_service.get_emoji_by_md5(emoji_md5)

        if not emoji_info:
            raise HTTPException(status_code=404, detail="Emoji not found")

        file_name = emoji_info.get('file_name', '')
        emoji_info['image_url'] = f"/static/emojis/{file_name}"

        return emoji_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting emoji: {str(e)}")


# ==================== Evaluation Endpoints ====================

class EvaluationRequest(BaseModel):
    """评估请求模型"""
    persona_id: int = Field(..., description="要评估的Persona ID")
    num_samples: int = Field(default=10, description="测试样本数量")
    include_ablation: bool = Field(default=True, description="是否包含消融实验")


class SingleEvaluationRequest(BaseModel):
    """单次评估请求模型"""
    generated: str = Field(..., description="生成的回复")
    reference: str = Field(..., description="参考回复")
    persona_id: Optional[int] = Field(default=None, description="可选的Persona ID")


@app.post("/api/evaluation/response-quality")
async def evaluate_response_quality(request: SingleEvaluationRequest):
    """
    评估单个回复的质量

    返回 BLEU 分数、语义相似度等指标
    """
    try:
        from evaluation import ResponseQualityEvaluator

        evaluator = ResponseQualityEvaluator()
        results = evaluator.evaluate_response(
            generated=request.generated,
            reference=request.reference
        )

        return {
            "status": "success",
            "metrics": [
                {
                    "name": r.metric_name,
                    "score": r.score,
                    "details": r.details
                }
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation error: {str(e)}")


@app.post("/api/evaluation/style-consistency")
async def evaluate_style_consistency(request: SingleEvaluationRequest):
    """
    评估回复与Persona风格的一致性
    """
    if not persona_service:
        raise HTTPException(status_code=503, detail="Persona service not initialized")

    try:
        from evaluation import PersonaStyleEvaluator

        evaluator = PersonaStyleEvaluator()

        # Get persona
        persona = None
        if request.persona_id:
            persona = persona_service.get_persona(request.persona_id)

        if not persona:
            return {
                "status": "error",
                "message": "Persona not found"
            }

        results = evaluator.evaluate_persona_imitation(
            generated=request.generated,
            persona=persona
        )

        return {
            "status": "success",
            "persona_name": persona.name,
            "metrics": [
                {
                    "name": r.metric_name,
                    "score": r.score,
                    "details": r.details
                }
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation error: {str(e)}")


@app.post("/api/evaluation/run-experiment")
async def run_evaluation_experiment(request: EvaluationRequest):
    """
    运行完整的评估实验

    包括：
    1. Baseline 对比实验
    2. 消融实验（可选）
    3. 生成评估报告
    """
    if not persona_service or not rag_service or not llm_service:
        raise HTTPException(status_code=503, detail="Services not initialized")

    try:
        from evaluation import (
            BaselineComparator, AblationStudy,
            EvaluationReportGenerator, ResponseQualityEvaluator
        )

        # Get persona
        persona = persona_service.get_persona(request.persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

        # Get test cases from chat history
        from database import ChatHistory, get_db
        db_session = get_db()
        chat_histories = db_session.query(ChatHistory).filter(
            ChatHistory.persona_id == request.persona_id
        ).limit(request.num_samples).all()

        if not chat_histories:
            raise HTTPException(status_code=400, detail="No chat history found for evaluation")

        test_cases = [
            {
                "user_message": h.user_message,
                "reference_response": h.assistant_response,
                "history": None
            }
            for h in chat_histories
        ]

        results = {}

        # Run baseline comparison
        comparator = BaselineComparator(llm_service, rag_service, persona_service)
        baseline_results = comparator.run_comparison_experiment(test_cases, request.persona_id)
        results["baseline_comparison"] = baseline_results

        # Run ablation study if requested
        if request.include_ablation:
            ablation = AblationStudy(llm_service, rag_service, persona_service, memory_service)
            ablation_results = ablation.run_ablation_study(test_cases[:5], request.persona_id)
            results["ablation_study"] = ablation_results

        # Generate report
        import os
        report_dir = os.path.join(PROJECT_ROOT, "evaluation_reports")
        os.makedirs(report_dir, exist_ok=True)

        report_path = os.path.join(report_dir, f"evaluation_{request.persona_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        # Generate LaTeX table for thesis
        if "metrics" in baseline_results:
            latex_path = os.path.join(report_dir, f"comparison_table_{request.persona_id}.tex")
            EvaluationReportGenerator.generate_latex_table(
                baseline_results["metrics"],
                latex_path
            )

        return {
            "status": "success",
            "persona_name": persona.name,
            "sample_count": len(test_cases),
            "baseline_metrics": baseline_results.get("metrics", {}),
            "report_path": report_path
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Experiment error: {str(e)}")


@app.get("/api/evaluation/test-cases/{persona_id}")
async def get_test_cases(persona_id: int, limit: int = 20):
    """
    获取用于评估的测试用例

    从聊天历史中提取测试样本
    """
    if not persona_service:
        raise HTTPException(status_code=503, detail="Persona service not initialized")

    try:
        from database import ChatHistory, get_db

        db_session = get_db()
        chat_histories = db_session.query(ChatHistory).filter(
            ChatHistory.persona_id == persona_id
        ).order_by(ChatHistory.imported_at.desc()).limit(limit).all()

        test_cases = [
            {
                "user_message": h.user_message,
                "reference_response": h.assistant_response,
                "topics": json.loads(h.topics) if h.topics else [],
                "sentiment": h.sentiment
            }
            for h in chat_histories
        ]

        return {
            "persona_id": persona_id,
            "count": len(test_cases),
            "test_cases": test_cases
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting test cases: {str(e)}")


# ==================== Entry Point ====================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("Digital Twin Chatbot Backend Server")
    print("=" * 60)
    print(f"API Docs: http://localhost:8000/docs")
    print(f"Health:  http://localhost:8000/api/health")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
