#!/bin/bash
# 表情包助手启动脚本 (Mac版)
# 使用方法: ./start.sh [backend|frontend|both]

# 激活conda环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate wxdata

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

case "$1" in
    backend)
        echo "启动后端服务..."
        cd "$SCRIPT_DIR/backend"
        python main.py
        ;;
    frontend)
        echo "启动前端服务..."
        cd "$SCRIPT_DIR/frontend"
        npm run dev
        ;;
    both|"")
        echo "同时启动前后端..."
        # 启动后端
        cd "$SCRIPT_DIR/backend"
        python main.py &
        BACKEND_PID=$!

        # 等待后端启动
        sleep 5

        # 启动前端
        cd "$SCRIPT_DIR/frontend"
        npm run dev &
        FRONTEND_PID=$!

        echo ""
        echo "=========================================="
        echo "服务已启动!"
        echo "  前端: http://localhost:5173"
        echo "  后端: http://localhost:8000"
        echo "  API文档: http://localhost:8000/docs"
        echo "=========================================="
        echo ""
        echo "按 Ctrl+C 停止所有服务"

        # 等待任意进程结束
        wait
        ;;
    *)
        echo "用法: $0 [backend|frontend|both]"
        exit 1
        ;;
esac