# 数字孪生对话智能体系统 - 使用说明

## 系统概述

这是一个基于 RAG (Retrieval-Augmented Generation) 的数字孪生对话智能体系统，能够：
- 模仿特定人物的聊天风格
- 自动从聊天记录中学习和提取人物特征
- 使用记忆系统记住用户偏好和重要信息
- 根据对话情境智能推荐表情包

## 核心组件

### 1. 数据库模型 (database.py)
- **Persona**: 数字孪生人物画像
- **ChatHistory**: 历史对话记录（用于RAG检索）
- **Memory**: 长期记忆系统
- **ChatSession**: 聊天会话管理
- **Message**: 消息记录

### 2. 聊天记录处理器 (chat_history_processor.py)
解析微信聊天记录导出文件，提取：
- 对话对（用户消息-人物回复）
- 人物性格特征分析
- 常用口头禅
- 表情使用偏好

### 3. 人物画像服务 (persona_service.py)
- 创建和管理数字孪生人物
- 导入聊天记录并分析人物特征
- 生成个性化系统提示词
- 提供相似对话检索

### 4. 记忆系统服务 (memory_service.py)
自动从对话中提取和记忆：
- 用户偏好（喜欢/不喜欢）
- 重要事实（工作、住址等）
- 事件信息（明天要做什么）
- 感兴趣的话题

### 5. 扩展RAG服务 (rag_service.py)
- 表情包检索（基于描述匹配）
- 相似对话检索（用于few-shot学习）

### 6. 改进的LLM服务 (llm_service.py)
- 支持个性化回复生成
- 集成人物画像和记忆上下文
- 支持流式响应

## API 接口

### 人物管理接口

#### 1. 列出所有人物
```
GET /api/personas
```

#### 2. 创建新人物
```
POST /api/personas
{
    "name": "示例人物",
    "description": "一个活泼可爱的数字孪生智能体",
    "avatar_url": "optional_avatar_url"
}
```

#### 3. 获取人物详情
```
GET /api/personas/{persona_id}
```

#### 4. 导入聊天记录
```
POST /api/personas/{persona_id}/import
Content-Type: multipart/form-data

file: [WeChat导出JSON文件]
persona_identifier: "示例人物" (可选，自动检测)
```

### 个性化聊天接口

#### 与数字孪生对话
```
POST /api/chat/personalized
{
    "message": "今天天气真好啊",
    "persona_id": 1,
    "session_id": 123,  // 可选，用于保持会话连续性
    "history": [  // 可选，历史消息
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好呀！"}
    ],
    "use_memory": true  // 是否使用记忆上下文
}
```

响应：
```json
{
    "text": "是啊，阳光明媚，适合出去走走~",
    "image_url": "/static/emojis/xxx.gif",
    "emoji_info": {
        "description": "开心的表情描述",
        "sub_category": "开心",
        "score": 0.85
    },
    "persona_id": 1,
    "session_id": 123,
    "memory_used": true
}
```

### 记忆管理接口

#### 获取人物的记忆
```
GET /api/personas/{persona_id}/memories?memory_type=fact
```

记忆类型：fact, preference, event, relationship, topic

### 传统聊天接口（保留兼容）

- `POST /api/chat` - 基础聊天
- `POST /api/chat/fast` - 快速聊天
- `GET /api/search?q=开心` - 搜索表情包
- `GET /api/emojis/random` - 随机表情包

## 使用流程

### 1. 初始化系统
```bash
cd backend
python main.py
```

### 2. 创建数字孪生人物
```bash
curl -X POST http://localhost:8000/api/personas \
  -H "Content-Type: application/json" \
  -d '{"name": "示例人物", "description": "数字孪生智能体"}'
```

### 3. 导入聊天记录
```bash
curl -X POST http://localhost:8000/api/personas/1/import \
  -F "file=@messages.json" \
  -F "persona_identifier=示例人物"
```

### 4. 开始对话
```bash
curl -X POST http://localhost:8000/api/chat/personalized \
  -H "Content-Type: application/json" \
  -d '{
    "message": "今天天气真好啊",
    "persona_id": 1,
    "use_memory": true
  }'
```

## 数据格式说明

### WeChat聊天记录导出格式 (messages.json)
```json
{
  "schemaVersion": 1,
  "exportedAt": "2025-12-29T08:38:09",
  "messages": [
    {
      "createTime": 1730206465,
      "createTimeText": "2024-10-29 20:54:25",
      "senderUsername": "wxid_xxx",
      "senderDisplayName": "示例人物",
      "type": 1,  // 1=文本, 47=表情, 3=图片
      "content": "消息内容"
    }
  ]
}
```

### 表情分类数据 (emoji_classification.jsonl)
每行一个JSON对象：
```json
{
  "top_category": "开心",
  "sub_category": "滑稽搞怪",
  "description": "表情描述文本...",
  "file_name": "006ca97248a1971ed95e5a1e4fb7dd9e.gif"
}
```

## 系统特点

1. **自动人物分析**: 从聊天记录自动提取口头禅、回复风格、表情偏好
2. **记忆系统**: 自动记住用户喜好、重要信息，让对话更个性化
3. **Few-shot学习**: 使用相似的历史对话作为示例，指导回复风格
4. **智能表情推荐**: 根据对话情境和人物偏好推荐合适的表情包
5. **渐进式学习**: 随着更多聊天记录导入，人物画像会越来越准确

## 毕业设计建议

### 可以添加的功能

1. **前端界面**
   - 人物选择器（切换不同数字孪生）
   - 聊天记录上传界面
   - 记忆查看和管理页面
   - 对话界面显示人物头像和表情

2. **评估系统**
   - 相似度评估（对比生成的回复和真实回复）
   - 用户满意度反馈
   - A/B测试不同参数的效果

3. **高级功能**
   - 多模态输入（语音、图片）
   - 群聊场景模拟
   - 情感分析可视化
   - 人物关系图谱

4. **优化方向**
   - 使用向量数据库存储对话嵌入（如ChromaDB、Milvus）
   - 实现真正的流式响应
   - 添加对话总结功能
   - 支持更多聊天平台数据导入

### 论文写作要点

1. **创新点**
   - 结合RAG和数字孪生概念
   - 自动人物画像生成
   - 记忆增强的对话系统

2. **实验设计**
   - 对比实验：有/无记忆系统
   - 人工评估：风格相似度评分
   - 消融实验：各组件的贡献

3. **技术亮点**
   - 使用LoRA微调本地模型（你已有的工作）
   - 混合检索策略（关键词+向量）
   - 动态提示词生成
