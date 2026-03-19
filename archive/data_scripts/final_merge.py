import json
import os
import re

# ================= 配置区域 =================
RAW_CHAT_FILE = 'wxdata_process\messages.json'       # 你的原始导出文件 (包含 messages 列表)
EMOJI_MAPPING_FILE = 'wxdata_process/emoji_mapping.json' # 刚才生成的表情包描述文件
OUTPUT_FILE = 'final_train_dataset.jsonl' # 最终输出给模型训练的文件

# 系统提示词 (System Prompt)
# 可以在这里微调你希望模型扮演的角色设定
SYSTEM_PROMPT = (
    "你是一个基于微信聊天记录训练的数字孪生智能体。"
    "你需要模仿[高雪洁]的说话风格、语气、口癖以及表情包使用习惯与[墨黎笙]进行对话。"
    "对话中要自然流露情绪，不要像个机器人。"
)

# 会话切分阈值 (分钟)
SESSION_THRESHOLD_MINUTES = 30 
# ===========================================

def load_emoji_mapping():
    if not os.path.exists(EMOJI_MAPPING_FILE):
        print(f"警告：找不到 {EMOJI_MAPPING_FILE}，表情包将不会被替换！")
        return {}
    
    with open(EMOJI_MAPPING_FILE, 'r', encoding='utf-8') as f:
        raw_map = json.load(f)
    
    # 清洗 key：去掉文件后缀 (.gif/.png)，只保留 MD5
    # 比如 "abcde123.gif" -> "abcde123"
    clean_map = {}
    for filename, caption in raw_map.items():
        key = filename.rsplit('.', 1)[0]
        clean_map[key] = caption
    
    print(f"已加载 {len(clean_map)} 个表情包描述。")
    return clean_map

def process_and_merge():
    # 1. 加载映射表
    emoji_map = load_emoji_mapping()
    
    # 2. 加载原始聊天记录
    print(f"正在读取原始聊天记录 {RAW_CHAT_FILE} ...")
    with open(RAW_CHAT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        messages = data.get('messages', []) if isinstance(data, dict) else data

    # 3. 按时间正序排序
    messages.sort(key=lambda x: x.get('createTime', 0))
    
    final_conversations = []
    current_session_msgs = []
    last_time = 0
    last_role = None
    buffer_content = [] 

    total_processed = 0
    replaced_emojis = 0

    print("开始融合数据...")

    for msg in messages:
        msg_type = msg.get('type')
        content = msg.get('content', '').strip()
        role = "user" if msg.get('isSent') else "assistant"
        timestamp = msg.get('createTime', 0)
        
        # --- 核心处理逻辑 ---
        
        final_content = ""

        # 情况 A: 文本消息 (通常 type=1)
        if msg_type == 1:
            if not content: continue
            # 过滤 XML 系统消息
            if content.startswith('<?xml') or '<msg>' in content: continue
            final_content = content

        # 情况 B: 表情包 (type=47)
        elif msg_type == 47:
            md5 = msg.get('emojiMd5')
            if md5 in emoji_map:
                final_content = emoji_map[md5]
                replaced_emojis += 1
            else:
                # 如果没识别出来，或者映射表里没有，选择跳过，还是保留占位符？
                # 建议：跳过，因为 "[表情]" 对模型没意义
                continue 

        # 其他类型 (图片/视频/引用) 暂时跳过
        else:
            continue

        if not final_content: continue

        total_processed += 1

        # --- 会话切分 (与之前逻辑相同) ---
        if last_time > 0 and (timestamp - last_time) > (SESSION_THRESHOLD_MINUTES * 60):
            if current_session_msgs:
                add_conversation(final_conversations, current_session_msgs)
                current_session_msgs = []
                last_role = None
                buffer_content = []

        # --- 连续发言合并 ---
        if role == last_role:
            buffer_content.append(final_content)
        else:
            if buffer_content and last_role:
                # 文本用空格连接，表情包如果是独立的，也可以直接连
                joined = " ".join(buffer_content)
                current_session_msgs.append({"role": last_role, "content": joined})
            
            buffer_content = [final_content]
            last_role = role
        
        last_time = timestamp

    # 处理最后遗留的 buffer
    if buffer_content and last_role:
        joined = " ".join(buffer_content)
        current_session_msgs.append({"role": last_role, "content": joined})
    
    if current_session_msgs:
        add_conversation(final_conversations, current_session_msgs)

    # --- 输出 ---
    print(f"\n处理完毕！")
    print(f"共生成对话组: {len(final_conversations)}")
    print(f"成功替换表情包: {replaced_emojis} 个")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for conv in final_conversations:
            f.write(json.dumps(conv, ensure_ascii=False) + '\n')
    
    print(f"最终训练数据已保存至: {OUTPUT_FILE}")

def add_conversation(final_list, raw_msgs):
    if len(raw_msgs) < 2: return
    # 确保 User 开头（可选）
    while raw_msgs and raw_msgs[0]['role'] == 'assistant':
        raw_msgs.pop(0)
    if not raw_msgs: return

    entry = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + raw_msgs
    }
    final_list.append(entry)

if __name__ == "__main__":
    process_and_merge()