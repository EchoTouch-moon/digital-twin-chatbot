import os
import base64
import json
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError

# -------------------------- 配置参数 --------------------------
DOUBAO_API_KEY = os.getenv("ARK_API_KEY") 
DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
MODEL_NAME = "doubao-seed-1-8-251228" # 【重要】请务必替换为你的 Endpoint ID (以 ep- 开头)，不要用模型名
EMOJI_DIR = " downloaded_media/emojis"
OUTPUT_JSONL_PATH = "./emoji_classification.jsonl"
ERROR_LOG_PATH = "./emoji_process_errors.log"
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

# 【性能核心】并发数量
# 建议从 5 开始尝试。如果是企业号可以开到 10-20。
# 免费号 QPS 较低，设太高会频繁报错。
MAX_WORKERS = 5 

# -------------------------- 初始化 --------------------------
logging.basicConfig(
    level=logging.INFO, # 改为 INFO 以便看到更多重试信息
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(ERROR_LOG_PATH), logging.StreamHandler()]
)

client = OpenAI(
    api_key=DOUBAO_API_KEY,
    base_url=DOUBAO_BASE_URL
)

# 文件写入锁，防止多线程同时写入导致文件乱码
file_lock = threading.Lock()

# -------------------------- 核心功能 --------------------------

def get_processed_files():
    """读取已处理的文件列表，实现断点续传"""
    processed = set()
    if os.path.exists(OUTPUT_JSONL_PATH):
        print("正在检查已有进度...")
        with open(OUTPUT_JSONL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    line = line.strip()
                    if not line: continue
                    data = json.loads(line)
                    # 假设结果里有 file_name 字段
                    if "file_name" in data:
                        processed.add(data["file_name"])
                except json.JSONDecodeError:
                    continue
    print(f"发现已有进度：{len(processed)} 张图片")
    return processed

def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded

def analyze_single_image(file_path):
    """
    单个图片处理函数（包含重试机制）
    """
    file_name = os.path.basename(file_path)
    
    prompt = """请你分析这张表情包的内容，严格按照以下要求输出JSON格式数据：
1. top_category: 从[开心, 生气, 伤心, 惊讶, 无奈, 嘲讽, 卖萌, 感动, 其他]中选一个
2. sub_category: 具体的场景细分
3. description: 详细描述画面、情绪及适用场景

输出JSON示例：
{"top_category":"开心","sub_category":"大笑","description":"..."}"""

    # 重试机制：如果遇到限流或网络错误，自动重试最多 3 次
    max_retries = 3
    for attempt in range(max_retries):
        try:
            image_b64 = image_to_base64(file_path)
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                            }
                        ]
                    }
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            result["file_name"] = file_name # 补全文件名
            return result

        except RateLimitError:
            # 遇到限流（429），等待时间随重试次数增加
            wait_time = (attempt + 1) * 2
            logging.warning(f"[{file_name}] 触发限流，等待 {wait_time}秒后重试...")
            time.sleep(wait_time)
        except (APIConnectionError, APIStatusError) as e:
            # 网络或其他API错误
            logging.warning(f"[{file_name}] API连接错误: {e}，正在重试...")
            time.sleep(1)
        except Exception as e:
            # 其他不可预知的错误（如JSON解析失败），不重试直接记录
            logging.error(f"[{file_name}] 处理失败: {e}")
            return None
    
    logging.error(f"[{file_name}] 重试 {max_retries} 次后依然失败，跳过。")
    return None

def save_result(result):
    """线程安全地写入结果"""
    if not result: return
    with file_lock:
        with open(OUTPUT_JSONL_PATH, "a", encoding="utf-8") as out_f:
            json.dump(result, out_f, ensure_ascii=False)
            out_f.write("\n")

# -------------------------- 主流程 --------------------------
def process_all_emojis_concurrently():
    # 1. 扫描本地文件
    all_files = [
        f for f in os.listdir(EMOJI_DIR)
        if f.lower().endswith(SUPPORTED_FORMATS)
    ]
    
    if not all_files:
        print(f"目录 {EMOJI_DIR} 为空！")
        return

    # 2. 获取已处理列表（断点续传）
    processed_files = get_processed_files()
    
    # 3. 过滤出待处理任务
    tasks = []
    for f in all_files:
        if f not in processed_files:
            tasks.append(os.path.join(EMOJI_DIR, f))
            
    print(f"总文件数: {len(all_files)} | 已完成: {len(processed_files)} | 待处理: {len(tasks)}")
    
    if not tasks:
        print("所有文件已处理完毕！")
        return

    # 4. 开启线程池并发处理
    print(f"开始并发处理，线程数: {MAX_WORKERS} ...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        # future_to_file = {executor.submit(analyze_single_image, file_path): file_path for file_path in tasks}
        
        # 使用 tqdm 显示进度条
        # 这里的 desc 会显示并发进度
        futures = [executor.submit(analyze_single_image, task) for task in tasks]
        
        for future in tqdm(as_completed(futures), total=len(tasks), desc="并发处理中"):
            try:
                result = future.result()
                if result:
                    save_result(result)
            except Exception as e:
                logging.error(f"线程异常: {e}")

    print(f"\n全部完成！结果已追加保存至 {OUTPUT_JSONL_PATH}")

if __name__ == "__main__":
    if not DOUBAO_API_KEY:
        print("错误：请配置环境变量 DOUBAO_API_KEY")
    else:
        # 确保目录存在
        if not os.path.exists(EMOJI_DIR):
            os.makedirs(EMOJI_DIR)
            print(f"已创建空目录 {EMOJI_DIR}，请放入图片后重试。")
        else:
            process_all_emojis_concurrently()