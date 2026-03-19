import json
import os
import requests
import hashlib

# ================= 配置 =================
INPUT_FILE = 'wxdata_process\messages.json'  # 你的原始导出文件
MEDIA_DIR = 'downloaded_media'    # 保存图片/表情的文件夹
# =======================================

def download_resource(url, save_dir, filename=None):
    if not url: return None
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    # 如果没有指定文件名，用 URL 的哈希做文件名
    if not filename:
        filename = hashlib.md5(url.encode()).hexdigest() + ".gif" # 表情通常是 gif 或 png
        
    save_path = os.path.join(save_dir, filename)
    
    if os.path.exists(save_path):
        return save_path # 已存在，跳过
        
    try:
        # 微信 CDN 通常不需要特殊 Header，但加上更稳
        headers = {'User-Agent': 'Mozilla/5.0'} 
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            return save_path
    except Exception as e:
        print(f"下载失败 {url}: {e}")
    return None

def process_media():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # 兼容列表或字典结构
        messages = data.get('messages', []) if isinstance(data, dict) else data

    print(f"开始扫描 {len(messages)} 条消息中的媒体文件...")
    
    count = 0
    for msg in messages:
        # 1. 处理表情包 (Emoji)
        if msg.get('type') == 47: # 表情包类型
            emoji_url = msg.get('emojiUrl')
            emoji_md5 = msg.get('emojiMd5')
            
            if emoji_url:
                # 使用 MD5 作为文件名，方便后续建立索引
                saved = download_resource(emoji_url, os.path.join(MEDIA_DIR, 'emojis'), filename=f"{emoji_md5}.gif")
                if saved: count += 1
                
        # 2. 处理图片 (Image) - 如果你的 JSON 里有 imageUrl
        # 注意：如果是本地路径 (dat文件)，需要另外的解密逻辑
        img_url = msg.get('imageUrl')
        if img_url and img_url.startswith('http'):
             download_resource(img_url, os.path.join(MEDIA_DIR, 'images'))

    print(f"下载完成！共处理 {count} 个文件。保存在 {MEDIA_DIR} 文件夹下。")

if __name__ == "__main__":
    process_media()