#!/usr/bin/env python3
"""
启动脚本 - 简化后端和前端的同时运行

使用方法:
    python run.py [backend|frontend|both]

参数:
    backend  - 只启动后端 (默认)
    frontend - 只启动前端
    both     - 同时启动后端和前端
"""

import subprocess
import sys
import os
import time


def run_backend():
    """启动 FastAPI 后端"""
    print("[Backend] Starting backend server...")
    print("   API docs: http://localhost:8000/docs")

    backend_dir = os.path.join(os.path.dirname(__file__), 'backend')

    process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'main:app', '--reload', '--port', '8000'],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8'
    )

    def log_output():
        for line in process.stdout:
            print(f"  [Backend] {line.strip()}")

    import threading
    log_thread = threading.Thread(target=log_output, daemon=True)
    log_thread.start()

    return process


def run_frontend():
    """启动 React 前端"""
    print("[Frontend] Starting frontend dev server...")
    print("   App: http://localhost:5173")

    frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')

    process = subprocess.Popen(
        ['npm', 'run', 'dev'],
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8'
    )

    def log_output():
        for line in process.stdout:
            print(f"  [Frontend] {line.strip()}")

    import threading
    log_thread = threading.Thread(target=log_output, daemon=True)
    log_thread.start()

    return process


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'backend'

    processes = []

    try:
        if cmd == 'backend':
            processes.append(run_backend())
        elif cmd == 'frontend':
            processes.append(run_frontend())
        elif cmd == 'both':
            processes.append(run_backend())
            time.sleep(3)
            processes.append(run_frontend())
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python run.py [backend|frontend|both]")
            return

        print("\n[OK] Services are running! Press Ctrl+C to stop.\n")

        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"Process exited with code {p.returncode}")
                    return

    except KeyboardInterrupt:
        print("\n\n[Stop] Stopping services...")
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=5)
            except:
                p.kill()
        print("[OK] All services stopped.")


if __name__ == '__main__':
    main()
