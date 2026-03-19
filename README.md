# 表情包助手 - RAG智能聊天机器人

一个基于 RAG (Retrieval-Augmented Generation) 的智能聊天机器人，能够根据用户的心情和对话内容，从表情包库中检索并推荐最合适的表情包。

## 项目架构

```
project/
├── backend/              # FastAPI 后端
│   ├── main.py          # FastAPI 主应用
│   ├── rag_service.py   # RAG 检索服务 (FAISS + Sentence-Transformers)
│   ├── llm_service.py   # LLM 服务 (OpenAI 兼容 API)
│   ├── requirements.txt # Python 依赖
│   └── .env             # 环境变量
├── frontend/            # React + Vite 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx    # 聊天界面
│   │   │   └── MessageBubble.jsx   # 消息气泡组件
│   │   ├── hooks/
│   │   │   └── useChat.js          # 聊天逻辑 Hook
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── emoji_classification.jsonl  # 表情包元数据
├── emojis/                     # 表情包图片文件夹
└── run.py                      # 一键启动脚本
```

## 核心功能

### 1. RAG 检索系统
- **向量化**: 使用 `sentence-transformers` (paraphrase-multilingual-MiniLM-L12-v2) 将表情包描述转换为向量
- **相似度搜索**: 使用 FAISS 进行高效的余弦相似度搜索
- **意图分析**: LLM 分析用户输入，提取搜索意图和关键词

### 2. 智能对话
- **多轮对话**: 支持上下文感知的对话历史
- **意图识别**: 自动判断是否需要推荐表情包
- **个性化回复**: 根据检索到的表情包生成相关回复

### 3. 微信风格界面
- **熟悉的 UI**: 仿微信聊天界面设计
- **消息气泡**: 支持文本、表情包图片展示
- **快速回复**: 预设快捷消息按钮
- **响应式**: 适配移动端和桌面端

## 快速开始

### 1. 环境准备

```bash
# Python 3.9+
python --version

# Node.js 18+
node --version

# npm 9+
npm --version
```

### 2. 安装依赖

**后端依赖:**
```bash
cd backend
pip install -r requirements.txt
```

**前端依赖:**
```bash
cd frontend
npm install
```

### 3. 配置环境变量

```bash
cd backend
cp .env.example .env
# 编辑 .env 文件，填入你的 OpenAI API Key
```

`.env` 文件示例:
```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo
```

### 4. 启动服务

**方式一: 使用一键启动脚本 (推荐)**
```bash
# 启动后端
python run.py backend

# 启动前端
python run.py frontend

# 同时启动前后端
python run.py both
```

**方式二: 手动启动**

终端 1 - 后端:
```bash
cd backend
python main.py
# 或
uvicorn main:app --reload --port 8000
```

终端 2 - 前端:
```bash
cd frontend
npm run dev
```

### 5. 访问应用

- **前端界面**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

## API 接口

### 健康检查
```
GET /api/health
```

### 聊天接口
```
POST /api/chat
Content-Type: application/json

{
  "message": "用户输入的消息",
  "history": [
    {"role": "user", "content": "历史消息1"},
    {"role": "assistant", "content": "历史回复1"}
  ]
}
```

**响应:**
```json
{
  "text": "AI 回复文本",
  "image_url": "/static/emojis/xxx.gif",
  "emoji_info": {
    "description": "表情包描述",
    "sub_category": "分类",
    "score": 0.85
  }
}
```

## 项目特点

### 技术优势
1. **RAG 架构**: 结合检索和生成，提供准确、相关的表情包推荐
2. **多语言支持**: 使用 multilingual 模型，支持中英文混合输入
3. **高效检索**: FAISS 向量索引，毫秒级相似度搜索
4. **模块化设计**: 服务分离，易于扩展和维护

### 用户体验
1. **零配置启动**: 一键启动脚本，无需繁琐配置
2. **实时响应**: 流式接口设计，低延迟响应
3. **优雅降级**: 服务异常时提供友好的错误提示
4. **移动优先**: 适配手机端，随时随地聊天

## 开发计划

- [x] 基础 RAG 检索系统
- [x] FastAPI 后端服务
- [x] React 前端界面
- [x] 微信风格 UI
- [ ] 用户历史记录持久化
- [ ] 表情包收藏功能
- [ ] 多模态输入 (语音/图片)
- [ ] 在线表情包搜索

## 贡献指南

欢迎提交 Issue 和 Pull Request!

## 许可证

MIT License

## 致谢

- [FastAPI](https://fastapi.tiangolo.com/)
- [FAISS](https://github.com/facebookresearch/faiss)
- [Sentence-Transformers](https://www.sbert.net/)
- [React](https://react.dev/)
- [Tailwind CSS](https://tailwindcss.com/)

---

<details>
<summary><strong>离线部署指南 (点击展开)</strong></summary>

### 使用 Docker 部署

```bash
# 构建镜僁
docker-compose up --build
```

### 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5173;
    }

    location /api {
        proxy_pass http://localhost:8000;
    }
}
```

</details>
