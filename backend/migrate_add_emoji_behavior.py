"""
数据库迁移脚本 - 添加表情包行为字段

为 Persona 表添加表情包行为分析相关字段：
- emoji_usage_frequency: 使用频率
- emoji_usage_rate: 使用率
- emoji_scenario_prefs: 场景偏好
- emoji_type_prefs: 类型偏好
"""

import os
import sys

# 添加backend目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from database import engine, get_db, init_database, Persona


def migrate_database():
    """执行数据库迁移"""
    print("开始数据库迁移...")

    # 先初始化数据库（创建新表/列）
    init_database()

    db = get_db()

    try:
        # 检查新列是否存在
        result = db.execute(text("PRAGMA table_info(personas)"))
        columns = [row[1] for row in result.fetchall()]

        print(f"当前列: {columns}")

        # 如果新列不存在，添加它们
        new_columns = [
            ("emoji_usage_frequency", "VARCHAR(20) DEFAULT 'medium'"),
            ("emoji_usage_rate", "FLOAT DEFAULT 0.5"),
            ("emoji_scenario_prefs", "JSON"),
            ("emoji_type_prefs", "JSON"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in columns:
                print(f"添加列: {col_name}")
                try:
                    db.execute(text(f"ALTER TABLE personas ADD COLUMN {col_name} {col_type}"))
                except Exception as e:
                    print(f"添加列 {col_name} 时出错 (可能已存在): {e}")

        db.commit()
        print("数据库迁移完成！")

    except Exception as e:
        print(f"迁移错误: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    migrate_database()