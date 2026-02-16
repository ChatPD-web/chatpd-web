from math import ceil
from typing import Dict, List, Optional, Tuple
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
QUERY_LOGIC_MODES = {"and", "or"}
DEFAULT_SORT_BY = "latest"
DEFAULT_SORT_ORDER = "desc"

ARXIV_TIME_SQL = """
CASE
    WHEN arxiv_id GLOB '[0-9][0-9][0-9][0-9].[0-9]*'
    THEN CAST(REPLACE(arxiv_id, '.', '') AS INTEGER)
    ELSE NULL
END
"""

SORTABLE_FIELDS = {
    "title": "title",
    "arxiv_id": "arxiv_id",
    "latest": ARXIV_TIME_SQL,
    "earliest": ARXIV_TIME_SQL,
    "dataset_name": "dataset_name",
    "dataset_entity": "dataset_entity",
    "task": "task",
    "data_type": "data_type",
    "scale": "scale",
    "location": "location",
}

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


def _parse_arxiv_month_key(month_value: Optional[str]) -> Optional[int]:
    if month_value is None:
        return None
    value = month_value.strip()
    if not value:
        return None
    if len(value) != 7 or value[4] != "-":
        raise ValueError("Invalid arxiv month format, expected YYYY-MM")
    year_part = value[:4]
    month_part = value[5:]
    if not year_part.isdigit() or not month_part.isdigit():
        raise ValueError("Invalid arxiv month format, expected YYYY-MM")
    year = int(year_part)
    month = int(month_part)
    if year < 1990 or year > 2099 or month < 1 or month > 12:
        raise ValueError("Invalid arxiv month range")
    return (year % 100) * 100 + month


def _build_condition_from_rule(rule: Dict) -> Tuple[str, List[str]]:
    field = (rule.get("field") or "all").strip()
    value = (rule.get("value") or "").strip()
    match_mode = (rule.get("match_mode") or "contains").strip()
    return _build_query_condition(value, field, match_mode)


def _validate_sort(sort_by: str, sort_order: str) -> Tuple[str, str]:
    sort_by = (sort_by or DEFAULT_SORT_BY).strip()
    sort_order = (sort_order or DEFAULT_SORT_ORDER).strip().lower()
    if sort_by not in SORTABLE_FIELDS:
        raise ValueError("Invalid sort_by")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("Invalid sort_order")
    if sort_by == "latest":
        sort_order = "desc"
    elif sort_by == "earliest":
        sort_order = "asc"
    return sort_by, sort_order


def _build_where_clause(
    q: str,
    field: str,
    match_mode: str,
    logic: str,
    conditions: Optional[List[Dict]],
) -> Tuple[str, List[str], List[Dict]]:
    rules = []
    sql_parts: List[str] = []
    params: List[str] = []

    logic = (logic or "and").strip().lower()
    if logic not in QUERY_LOGIC_MODES:
        raise ValueError("Invalid logic")

    for rule in (conditions or []):
        if not isinstance(rule, dict):
            continue
        value = (rule.get("value") or "").strip()
        if not value:
            continue
        clause, clause_params = _build_condition_from_rule(rule)
        sql_parts.append(clause)
        params.extend(clause_params)
        rules.append(
            {
                "field": (rule.get("field") or "all").strip(),
                "value": value,
                "match_mode": (rule.get("match_mode") or "contains").strip(),
            }
        )

    if not sql_parts and (q or "").strip():
        clause, clause_params = _build_query_condition(q.strip(), field, match_mode)
        sql_parts.append(clause)
        params.extend(clause_params)
        rules.append(
            {
                "field": field,
                "value": q.strip(),
                "match_mode": match_mode,
            }
        )

    if not sql_parts:
        return "", [], []

    joined = f" {logic.upper()} ".join([f"({part})" for part in sql_parts])
    return f" WHERE {joined}", params, rules


def _distribution_sql(where_clause: str, field_name: str) -> str:
    extra_where = (
        f"{where_clause} AND {field_name} IS NOT NULL AND {field_name} != ''"
        if where_clause
        else f" WHERE {field_name} IS NOT NULL AND {field_name} != ''"
    )
    return f"""
        SELECT {field_name} AS name, COUNT(*) AS count
        FROM dataset_usage
        {extra_where}
        GROUP BY {field_name}
        ORDER BY count DESC, name ASC
        LIMIT 12
    """


def search_records(
    q: str,
    field: str = "all",
    match_mode: str = "contains",
    page: int = 1,
    per_page: int = 10,
    logic: str = "and",
    conditions: Optional[List[Dict]] = None,
    sort_by: str = DEFAULT_SORT_BY,
    sort_order: str = DEFAULT_SORT_ORDER,
    include_stats: bool = False,
    arxiv_from: Optional[str] = None,
    arxiv_to: Optional[str] = None,
) -> Dict:
    q = (q or "").strip()
    page = max(int(page), 1)
    per_page = min(max(int(per_page), 1), 50)
    field = (field or "all").strip()
    match_mode = (match_mode or "contains").strip()
    include_stats = bool(include_stats)

    if field not in QUERYABLE_FIELDS:
        raise ValueError("Invalid field")
    if match_mode not in QUERY_MATCH_MODES:
        raise ValueError("Invalid match_mode")
    sort_by, sort_order = _validate_sort(sort_by, sort_order)

    where_clause, params, effective_rules = _build_where_clause(
        q=q,
        field=field,
        match_mode=match_mode,
        logic=logic,
        conditions=conditions,
    )

    arxiv_from_key = _parse_arxiv_month_key(arxiv_from)
    arxiv_to_key = _parse_arxiv_month_key(arxiv_to)
    if arxiv_from_key is not None and arxiv_to_key is not None and arxiv_from_key > arxiv_to_key:
        raise ValueError("arxiv_from must be earlier than or equal to arxiv_to")

    time_sql_parts: List[str] = []
    time_params: List[int] = []
    if arxiv_from_key is not None:
        time_sql_parts.append(f"({ARXIV_TIME_SQL}) >= ?")
        time_params.append(arxiv_from_key * 100)
    if arxiv_to_key is not None:
        time_sql_parts.append(f"({ARXIV_TIME_SQL}) <= ?")
        time_params.append(arxiv_to_key * 100 + 99)

    if time_sql_parts:
        time_clause = " AND ".join(time_sql_parts)
        if where_clause:
            where_clause = f"{where_clause} AND {time_clause}"
        else:
            where_clause = f" WHERE {time_clause}"
        params.extend(time_params)

    sort_column = SORTABLE_FIELDS[sort_by]

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
            ORDER BY {sort_column} {sort_order.upper()}, title ASC
            LIMIT ? OFFSET ?
        """
        offset = (page - 1) * per_page
        cursor.execute(query_sql, params + [per_page, offset])
        rows = [dict(row) for row in cursor.fetchall()]

        stats = None
        if include_stats:
            task_sql = _distribution_sql(where_clause, "task")
            cursor.execute(task_sql, params)
            task_distribution = [dict(row) for row in cursor.fetchall()]

            data_type_sql = _distribution_sql(where_clause, "data_type")
            cursor.execute(data_type_sql, params)
            data_type_distribution = [dict(row) for row in cursor.fetchall()]

            stats = {
                "task_distribution": task_distribution,
                "data_type_distribution": data_type_distribution,
            }
    finally:
        return_db_connection(conn)

    response = {
        "results": rows,
        "results_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "per_page": per_page,
        "returned_count": len(rows),
        "query_meta": {
            "query": q,
            "field": field,
            "match_mode": match_mode,
            "logic": logic,
            "conditions": effective_rules,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "include_stats": include_stats,
            "arxiv_from": arxiv_from.strip() if isinstance(arxiv_from, str) else None,
            "arxiv_to": arxiv_to.strip() if isinstance(arxiv_to, str) else None,
        },
    }
    if stats is not None:
        response["stats"] = stats
    return response


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
