import json
import sqlite3
import pandas as pd

# 读取 JSON 文件
json_file = "data/final_product/ChatPD_WebData.json"
with open(json_file, "r", encoding="utf-8") as file:
    data = json.load(file)  # 解析 JSON 文件

# 连接 SQLite 数据库
db_file = "data/chatpd_data.db"
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# 先删除表（如果已存在）以避免主键定义冲突
cursor.execute('DROP TABLE IF EXISTS dataset_usage')

# 创建表，使用 arxiv_id 和 dataset_name 的组合作为主键
cursor.execute('''
    CREATE TABLE IF NOT EXISTS dataset_usage (
        arxiv_id TEXT,
        dataset_name TEXT,
        title TEXT,
        dataset_summary TEXT,
        task TEXT,
        data_type TEXT,
        location TEXT,
        scale TEXT,
        dataset_citation TEXT,
        dataset_provider TEXT,
        dataset_url TEXT,
        dataset_publicly_available TEXT,
        other_info TEXT,
        entity_name TEXT,
        dataset_entity TEXT,
        papers_with_code_url TEXT,
        homepage TEXT,
        PRIMARY KEY (arxiv_id, dataset_name)
    )
''')

# 使用 REPLACE 插入数据，以确保更新现有记录
for entry in data:
    cursor.execute('''
        REPLACE INTO dataset_usage (
            arxiv_id, dataset_name, title, dataset_summary, task, data_type, location, scale,
            dataset_citation, dataset_provider, dataset_url, dataset_publicly_available,
            other_info, entity_name, dataset_entity, papers_with_code_url, homepage
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        entry.get("arxiv id"),
        entry.get("dataset name"),
        entry.get("title"),
        entry.get("dataset summary"),
        entry.get("task"),
        entry.get("data type"),
        entry.get("location"),
        entry.get("scale"),
        entry.get("dataset citation"),
        entry.get("dataset provider"),
        entry.get("dataset url"),
        entry.get("dataset publicly available"),
        entry.get("other useful information about this dataset"),
        entry.get("entity_name"),
        entry.get("dataset entity"),
        entry.get("PapersWithCode URL"),
        entry.get("homepage")
    ))

# 提交更改并关闭连接
conn.commit()
conn.close()
print("数据已成功保存到数据库")
