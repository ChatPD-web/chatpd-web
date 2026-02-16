from math import ceil
from typing import Dict, List, Tuple
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data/chatpd_data.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def return_db_connection(conn):
    conn.close()

# 用户可用查询字段映射
QUERYABLE_FIELDS = {
    "all": None,
    "arxiv_id": "arxiv_id",
    "title": "title",
    "dataset_name": "dataset_name",
    "dataset_entity": "dataset_entity",
    "task": "task",
    "data_type": "data_type",
}

QUERY_MATCH_MODES = {"contains", "exact", "prefix"}

SELECT_FIELDS = """
    arxiv_id,
    CASE
        WHEN title IS NULL OR title = 'None' OR title = '' THEN
            COALESCE(
                (SELECT title FROM dataset_usage du2
                 WHERE du2.arxiv_id = dataset_usage.arxiv_id
                 AND du2.title IS NOT NULL
                 AND du2.title != 'None'
                 AND du2.title != ''
                 LIMIT 1),
                'arXiv:' || arxiv_id
            )
        ELSE title
    END as title,
    dataset_name, dataset_summary, task, data_type,
    location, scale, dataset_url, dataset_entity, other_info, homepage
"""


def _build_like_term(q: str, match_mode: str) -> str:
    if match_mode == "exact":
        return q
    if match_mode == "prefix":
        return f"{q}%"
    return f"%{q}%"


def _build_query_condition(q: str, field: str, match_mode: str) -> Tuple[str, List[str]]:
    if not q:
        return "", []

    if field not in QUERYABLE_FIELDS:
        raise ValueError("Invalid field")
    if match_mode not in QUERY_MATCH_MODES:
        raise ValueError("Invalid match_mode")

    if match_mode == "exact":
        operator = "="
    else:
        operator = "LIKE"

    if field == "all":
        term = _build_like_term(q, match_mode)
        columns = [
            "arxiv_id",
            "title",
            "dataset_name",
            "dataset_entity",
            "dataset_summary",
            "task",
            "data_type",
        ]
        clause = "(" + " OR ".join([f"{col} {operator} ?" for col in columns]) + ")"
        return clause, [term] * len(columns)

    term = _build_like_term(q, match_mode)
    column = QUERYABLE_FIELDS[field]
    return f"{column} {operator} ?", [term]


def search_records(q: str, field: str = "all", match_mode: str = "contains", page: int = 1, per_page: int = 10) -> Dict:
    q = (q or "").strip()
    page = max(int(page), 1)
    per_page = min(max(int(per_page), 1), 50)

    condition, params = _build_query_condition(q, field, match_mode)
    where_clause = f" WHERE {condition}" if condition else ""

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        count_sql = f"SELECT COUNT(*) AS count FROM dataset_usage{where_clause}"
        cursor.execute(count_sql, params)
        total_count = cursor.fetchone()["count"]
        total_pages = ceil(total_count / per_page) if total_count else 0

        query_sql = f"""
            SELECT {SELECT_FIELDS}
            FROM dataset_usage
            {where_clause}
            ORDER BY title
            LIMIT ? OFFSET ?
        """
        offset = (page - 1) * per_page
        cursor.execute(query_sql, params + [per_page, offset])
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        return_db_connection(conn)

    return {
        "results": rows,
        "results_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "field": field,
        "match_mode": match_mode,
        "query": q,
    }


def get_records_by_arxiv_id(arxiv_id: str) -> List[Dict]:
    arxiv_id = (arxiv_id or "").strip()
    if not arxiv_id:
        return []

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {SELECT_FIELDS}
            FROM dataset_usage
            WHERE arxiv_id = ?
            ORDER BY dataset_entity, dataset_name
            """,
            (arxiv_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        return_db_connection(conn)
