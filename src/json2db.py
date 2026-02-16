import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


JSON_FILE = os.getenv("CHATPD_JSON_FILE", "data/final_product/ChatPD_WebData_from_db.json")
DB_FILE = os.getenv("CHATPD_DB_FILE", "data/chatpd_data.db")
BATCH_SIZE = int(os.getenv("CHATPD_BATCH_SIZE", "2000"))
COMMIT_EVERY = int(os.getenv("CHATPD_COMMIT_EVERY", "20000"))

INSERT_SQL = """
    REPLACE INTO dataset_usage (
        arxiv_id, dataset_name, title, dataset_summary, task, data_type, location, scale,
        dataset_citation, dataset_provider, dataset_url, dataset_publicly_available,
        other_info, entity_name, dataset_entity, papers_with_code_url, homepage,
        arxiv_time_key, arxiv_yymm_key
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def iter_json_array(path: str, chunk_size: int = 256 * 1024) -> Iterator[Dict]:
    """Stream parse a top-level JSON array with stable memory usage."""
    started = False
    current_chars: List[str] = []
    depth = 0
    in_string = False
    escape = False

    with open(path, "r", encoding="utf-8") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break

            for ch in chunk:
                if not started:
                    if ch.isspace():
                        continue
                    if ch != "[":
                        raise ValueError("JSON root must be an array.")
                    started = True
                    continue

                if depth == 0:
                    if ch.isspace() or ch == ",":
                        continue
                    if ch == "]":
                        return
                    if ch != "{":
                        raise ValueError("Array item must be a JSON object.")
                    current_chars = ["{"]
                    depth = 1
                    in_string = False
                    escape = False
                    continue

                current_chars.append(ch)

                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue

                if ch == '"':
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                    continue
                if ch == "}":
                    depth -= 1
                    if depth == 0:
                        obj_text = "".join(current_chars)
                        obj = json.loads(obj_text)
                        if not isinstance(obj, dict):
                            raise ValueError("Each array item must be an object.")
                        yield obj
                        current_chars = []

    if depth != 0:
        raise ValueError("Unexpected end of JSON input.")


def get_value(entry: Dict, *keys: str):
    for key in keys:
        if key in entry:
            return entry.get(key)
    return None


def parse_arxiv_keys(arxiv_id_value) -> Tuple[Optional[int], Optional[int]]:
    if not isinstance(arxiv_id_value, str):
        return None, None
    arxiv_id = arxiv_id_value.strip()
    if not re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", arxiv_id):
        return None, None
    raw = arxiv_id.split("v", 1)[0]
    yymm = int(raw[:4])
    time_key = int(raw.replace(".", ""))
    return time_key, yymm


def to_row(entry: Dict) -> Tuple:
    arxiv_id = get_value(entry, "arxiv id", "arxiv_id")
    arxiv_time_key, arxiv_yymm_key = parse_arxiv_keys(arxiv_id)
    return (
        arxiv_id,
        get_value(entry, "dataset name", "dataset_name"),
        get_value(entry, "title"),
        get_value(entry, "dataset summary", "dataset_summary"),
        get_value(entry, "task"),
        get_value(entry, "data type", "data_type"),
        get_value(entry, "location"),
        get_value(entry, "scale"),
        get_value(entry, "dataset citation", "dataset_citation"),
        get_value(entry, "dataset provider", "dataset_provider"),
        get_value(entry, "dataset url", "dataset_url"),
        get_value(entry, "dataset publicly available", "dataset_publicly_available"),
        get_value(entry, "other useful information about this dataset", "other_info"),
        get_value(entry, "entity_name"),
        get_value(entry, "dataset entity", "dataset_entity"),
        get_value(entry, "PapersWithCode URL", "papers_with_code_url"),
        get_value(entry, "homepage"),
        arxiv_time_key,
        arxiv_yymm_key,
    )


def batched_rows(entries: Iterable[Dict], size: int) -> Iterator[List[Tuple]]:
    batch: List[Tuple] = []
    for entry in entries:
        batch.append(to_row(entry))
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS dataset_usage")
    cursor.execute(
        """
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
            arxiv_time_key INTEGER,
            arxiv_yymm_key INTEGER,
            PRIMARY KEY (arxiv_id, dataset_name)
        )
        """
    )

    imported = 0
    for batch in batched_rows(iter_json_array(JSON_FILE), BATCH_SIZE):
        cursor.executemany(INSERT_SQL, batch)
        imported += len(batch)
        if imported % COMMIT_EVERY == 0:
            conn.commit()
        if imported % 50000 == 0:
            print(f"Imported {imported} records...")

    conn.commit()
    conn.close()

    print(f"数据已成功保存到数据库: {DB_FILE}")
    print(f"数据源: {JSON_FILE}")
    print(f"导入记录数: {imported}")
    print(f"更新时间: {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
