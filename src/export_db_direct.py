#!/usr/bin/env python3
"""
直接从 chatpd_qwen.db 生成 web 端 chatpd_data.db，跳过 JSON 中间文件。

用法:
    python src/export_db_direct.py [--output-db data/chatpd_data.db]
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from typing import Optional

# 将 ChatPD scripts 目录加入 path，复用实体解析和数据融合模块
# web_chatpd/ 和 ChatPD/ 都在 ~/xaj/Program/ 下
_script_dir = os.path.dirname(os.path.abspath(__file__))  # .../web_chatpd/web_chatpd/src
_web_project_root = os.path.dirname(_script_dir)  # .../web_chatpd/web_chatpd
_PROGRAM_DIR = os.path.dirname(os.path.dirname(_web_project_root))  # .../Program
CHATPD_SCRIPTS = os.path.join(_PROGRAM_DIR, "ChatPD", "scripts")
sys.path.insert(0, CHATPD_SCRIPTS)

from simple_entity_resolution import (
    build_pwc_name_index,
    resolve_entity,
    is_meaningless_name,
    PWC_DATASETS_PATH,
    CURATED_DATASETS_PATH,
)
from data_fusion import clean_record, add_pwc_info

# 复用 export_webdata_from_db 中的数据加载和 title backfill 函数
from export_webdata_from_db import load_descriptions_from_db, backfill_titles_from_metadata_shards

# ============================================================================
# 配置路径
# ============================================================================

WEB_PROJECT_ROOT = _web_project_root
CHATPD_ROOT = os.path.join(_PROGRAM_DIR, "ChatPD")

DB_SOURCE_PATH = os.path.join(CHATPD_ROOT, "data", "chatpd_qwen.db")
DEFAULT_DB_OUTPUT = os.path.join(WEB_PROJECT_ROOT, "data", "chatpd_data.db")
DEFAULT_METADATA_SHARDS = os.path.join(CHATPD_ROOT, "data", "metadata_shards", "440a1dd18dadf9d5")

CREATE_TABLE_SQL = """
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
"""

INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS idx_data_type ON dataset_usage(data_type);",
    "CREATE INDEX IF NOT EXISTS idx_task ON dataset_usage(task);",
    "CREATE INDEX IF NOT EXISTS idx_dataset_entity ON dataset_usage(dataset_entity);",
    "CREATE INDEX IF NOT EXISTS idx_arxiv_id ON dataset_usage(arxiv_id);",
    "CREATE INDEX IF NOT EXISTS idx_title ON dataset_usage(title);",
    "CREATE INDEX IF NOT EXISTS idx_dataset_name ON dataset_usage(dataset_name);",
    "CREATE INDEX IF NOT EXISTS idx_data_type_task ON dataset_usage(data_type, task);",
]


def main():
    parser = argparse.ArgumentParser(description="直接从 chatpd_qwen.db 生成 web 数据库")
    parser.add_argument("--output-db", default=DEFAULT_DB_OUTPUT, help="输出 SQLite 数据库路径")
    parser.add_argument("--source-db", default=DB_SOURCE_PATH, help="源数据库路径")
    parser.add_argument("--metadata-shards", default=DEFAULT_METADATA_SHARDS, help="arXiv metadata shards 目录")
    args = parser.parse_args()

    t0 = time.time()

    # 1. 加载 PWC 数据集库
    print("[1/6] 加载 PWC 数据集库...")
    with open(PWC_DATASETS_PATH, "r", encoding="utf-8") as f:
        pwc_datasets = json.load(f)
    print(f"  PWC 数据集: {len(pwc_datasets)}")

    curated_datasets = []
    if os.path.exists(CURATED_DATASETS_PATH):
        with open(CURATED_DATASETS_PATH, "r", encoding="utf-8") as f:
            curated_datasets = json.load(f)
        print(f"  ChatPD curated: {len(curated_datasets)}")

    pwc_index = build_pwc_name_index(pwc_datasets, curated_datasets)
    pwc_name_to_dataset = {d["name"]: d for d in pwc_datasets}
    for d in curated_datasets:
        pwc_name_to_dataset[d["name"]] = d

    # 2. 从源数据库加载数据
    print("[2/6] 从 chatpd_qwen.db 加载数据...")
    all_descs = load_descriptions_from_db(args.source_db)
    print(f"  原始记录: {len(all_descs)}")

    # 3. 过滤无意义记录
    print("[3/6] 过滤 + 实体解析 + 清洗 + PWC...")
    valid = []
    matched = 0
    for desc in all_descs:
        name = desc.get("dataset name")
        if not name or is_meaningless_name(name):
            continue
        arxiv_id = desc.get("arxiv id")
        if not arxiv_id:
            continue

        entity = resolve_entity(name, pwc_index)
        desc["dataset entity"] = entity
        if entity:
            matched += 1

        clean_record(desc)
        for key in ["identifier", "entity_name"]:
            desc.pop(key, None)
        add_pwc_info(desc, pwc_name_to_dataset)
        valid.append(desc)

    print(f"  有效记录: {len(valid)} (实体匹配: {matched}/{len(valid)})")

    # 4. Title backfill
    print("[4/6] arXiv metadata title backfill...")
    title_stats = backfill_titles_from_metadata_shards(valid, args.metadata_shards)
    print(f"  补齐: {title_stats['records_backfilled']}, 未补齐: {title_stats['records_unresolved']}")

    # 5. 写入 SQLite（批量写入提高性能）
    print("[5/6] 写入 SQLite 数据库...")
    os.makedirs(os.path.dirname(args.output_db), exist_ok=True)

    conn = sqlite3.connect(args.output_db)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS dataset_usage")
    cursor.execute(CREATE_TABLE_SQL)

    insert_sql = """
        INSERT INTO dataset_usage (
            arxiv_id, dataset_name, title, dataset_summary, task, data_type,
            location, scale, dataset_citation, dataset_provider, dataset_url,
            dataset_publicly_available, other_info, entity_name, dataset_entity,
            papers_with_code_url, homepage
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    batch_size = 5000
    batch = []
    for rec in valid:
        batch.append((
            rec.get("arxiv id"),
            rec.get("dataset name"),
            rec.get("title"),
            rec.get("dataset summary"),
            rec.get("task"),
            rec.get("data type"),
            rec.get("location"),
            rec.get("scale"),
            rec.get("dataset citation"),
            rec.get("dataset provider"),
            rec.get("dataset url"),
            rec.get("dataset publicly available"),
            rec.get("other useful information about this dataset"),
            rec.get("entity_name"),
            rec.get("dataset entity"),
            rec.get("PapersWithCode URL"),
            rec.get("homepage"),
        ))
        if len(batch) >= batch_size:
            cursor.executemany(insert_sql, batch)
            batch.clear()

    if batch:
        cursor.executemany(insert_sql, batch)

    conn.commit()

    # 6. 创建索引
    print("[6/6] 创建索引...")
    for idx_sql in INDEX_SQLS:
        cursor.execute(idx_sql)
    conn.commit()
    conn.close()

    # 统计
    arxiv_ids = len(set(r.get("arxiv id") for r in valid))
    entities = len(set(r.get("dataset entity") for r in valid if r.get("dataset entity")))
    size_mb = os.path.getsize(args.output_db) / (1024 * 1024)

    elapsed = time.time() - t0
    print(f"\n完成! 耗时 {elapsed:.1f}s")
    print(f"  记录: {len(valid)} / 论文: {arxiv_ids} / 数据集: {entities}")
    print(f"  数据库大小: {size_mb:.0f} MB")
    print(f"  输出: {args.output_db}")


if __name__ == "__main__":
    main()
