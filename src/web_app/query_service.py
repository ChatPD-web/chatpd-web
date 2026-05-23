from functools import lru_cache
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

ARXIV_YYMM_SQL = """
CASE
    WHEN arxiv_id GLOB '[0-9][0-9][0-9][0-9].[0-9]*'
    THEN CAST(SUBSTR(arxiv_id, 1, 4) AS INTEGER)
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
    if len(value) != 4 or not value.isdigit():
        raise ValueError("Invalid arxiv month format, expected YYMM")
    yy = int(value[:2])
    mm = int(value[2:])
    if mm < 1 or mm > 12:
        raise ValueError("Invalid arxiv month range")
    return yy * 100 + mm


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
        time_sql_parts.append(f"({ARXIV_YYMM_SQL}) >= ?")
        time_params.append(arxiv_from_key)
    if arxiv_to_key is not None:
        time_sql_parts.append(f"({ARXIV_YYMM_SQL}) <= ?")
        time_params.append(arxiv_to_key)

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


# ============================================================================
# AI context and graph data helpers
# ============================================================================


@lru_cache(maxsize=256)
def get_related_datasets(dataset_entity: str, top_n: int = 20) -> Dict:
    """Return datasets that co-occur with the given dataset in papers."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d2.dataset_entity, COUNT(DISTINCT d1.arxiv_id) as co_usage_count
            FROM dataset_usage d1
            JOIN dataset_usage d2 ON d1.arxiv_id = d2.arxiv_id
            WHERE d1.dataset_entity = ?
              AND d2.dataset_entity != ?
              AND d2.dataset_entity IS NOT NULL AND d2.dataset_entity != ''
            GROUP BY d2.dataset_entity
            ORDER BY co_usage_count DESC
            LIMIT ?
        """, (dataset_entity, dataset_entity, top_n))
        related = [dict(row) for row in cursor.fetchall()]

        total_count = 0
        if related:
            cursor.execute("""
                SELECT COUNT(DISTINCT d2.dataset_entity)
                FROM dataset_usage d1
                JOIN dataset_usage d2 ON d1.arxiv_id = d2.arxiv_id
                WHERE d1.dataset_entity = ?
                  AND d2.dataset_entity != ?
                  AND d2.dataset_entity IS NOT NULL AND d2.dataset_entity != ''
            """, (dataset_entity, dataset_entity))
            row = cursor.fetchone()
            total_count = row[0] if row else 0

        related_mapped = [
            {"entity": r["dataset_entity"], "co_usage_count": r["co_usage_count"]}
            for r in related
        ]

        return {
            "dataset_entity": dataset_entity,
            "related": related_mapped,
            "total_related": total_count,
        }
    finally:
        return_db_connection(conn)


@lru_cache(maxsize=256)
def get_dataset_trends(dataset_entity: str) -> Dict:
    """Return monthly and yearly usage trends for a dataset."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUBSTR(arxiv_id, 1, 2) || SUBSTR(arxiv_id, 3, 2) AS year_month,
                   COUNT(DISTINCT arxiv_id) as paper_count
            FROM dataset_usage
            WHERE dataset_entity = ?
              AND arxiv_id GLOB '[0-9][0-9][0-9][0-9].[0-9]*'
            GROUP BY year_month ORDER BY year_month
        """, (dataset_entity,))
        monthly = [dict(row) for row in cursor.fetchall()]

        yearly = {}
        for m in monthly:
            ym = str(m["year_month"])
            if len(ym) == 4:
                year = 2000 + int(ym[:2])
                yearly[year] = yearly.get(year, 0) + m["paper_count"]

        yearly_summary = [
            {"year": y, "paper_count": c}
            for y, c in sorted(yearly.items())
        ]

        return {
            "dataset_entity": dataset_entity,
            "trends": monthly,
            "yearly_summary": yearly_summary,
        }
    finally:
        return_db_connection(conn)


def build_ai_context_for_dataset(dataset_entity: str, records: List[Dict]) -> Dict:
    """Build _ai_context for dataset detail responses."""
    arxiv_ids = set(r["arxiv_id"] for r in records if r.get("arxiv_id"))
    total_papers = len(arxiv_ids)

    task_counts: Dict[str, int] = {}
    for r in records:
        task = r.get("task")
        if task:
            task_counts[task] = task_counts.get(task, 0) + 1

    top_tasks = sorted(task_counts.items(), key=lambda x: -x[1])[:5]

    related_raw = get_related_datasets(dataset_entity, 5)
    most_related = related_raw["related"]

    trends_data = get_dataset_trends(dataset_entity)
    yearly = trends_data.get("yearly_summary", [])
    peak_year = None
    peak_count = 0
    if yearly:
        peak = max(yearly, key=lambda y: y["paper_count"])
        peak_year = peak["year"]
        peak_count = peak["paper_count"]

    trend = "stable"
    trend_detail = "No significant change in the last 3 years"
    if len(yearly) >= 3:
        recent = yearly[-3:]
        n = len(recent)
        xs = list(range(n))
        ys = [y["paper_count"] for y in recent]
        mean_y = sum(ys) / n
        num = sum((xs[i] - (n - 1) / 2) * (ys[i] - mean_y) for i in range(n))
        den = sum((xs[i] - (n - 1) / 2) ** 2 for i in range(n))
        slope = (num / den) if den != 0 else 0
        slope_pct = (slope / mean_y * 100) if mean_y > 0 else 0

        if slope_pct > 10:
            trend = "rising"
        elif slope_pct > 0:
            trend = "stable_growth"
        elif slope_pct == 0:
            trend = "stable"
        else:
            trend = "declining"

        direction = "Growing" if slope_pct > 0 else "Declining"
        trend_detail = (
            f"{direction} {abs(round(slope_pct))}% per year over the last {n} years"
        )

    return {
        "entity": dataset_entity,
        "total_papers": total_papers,
        "trend": trend,
        "trend_detail": trend_detail,
        "peak_year": peak_year,
        "peak_year_count": peak_count,
        "top_tasks": [{"task": t, "count": c} for t, c in top_tasks],
        "most_related_datasets": most_related,
    }


def build_ai_context_for_paper(records: List[Dict]) -> Dict:
    """Build _ai_context for paper detail responses."""
    datasets = sorted(set(
        r.get("dataset_entity") for r in records
        if r.get("dataset_entity")
    ))
    tasks = sorted(set(
        r.get("task") for r in records if r.get("task")
    ))
    data_types = sorted(set(
        r.get("data_type") for r in records if r.get("data_type")
    ))
    arxiv_id = records[0].get("arxiv_id") if records else None
    title = records[0].get("title") if records else None
    return {
        "arxiv_id": arxiv_id,
        "paper_title": title,
        "dataset_count": len(datasets),
        "dataset_entities": datasets,
        "unique_tasks": tasks,
        "unique_data_types": data_types,
    }


def build_ai_context_for_query(results_count: int, q: str, results: List[Dict]) -> Dict:
    """Build _ai_context for query/search responses."""
    datasets = set()
    papers = set()
    top_dataset = None
    top_task = None
    task_counts: Dict[str, int] = {}
    for r in results:
        if r.get("dataset_entity"):
            datasets.add(r["dataset_entity"])
            if top_dataset is None:
                top_dataset = r["dataset_entity"]
        if r.get("arxiv_id"):
            papers.add(r["arxiv_id"])
        task = r.get("task")
        if task:
            task_counts[task] = task_counts.get(task, 0) + 1

    if task_counts:
        top_task = max(task_counts, key=task_counts.get)

    query_summary = (
        f"Found {results_count:,} records matching '{q}' "
        f"across {len(datasets):,} datasets and {len(papers):,} papers"
    )

    suggested = []
    if top_task:
        suggested.append(f"Refine: add task={top_task} to narrow results")
    if top_dataset:
        suggested.append(
            f"Explore: GET /api/dataset/{top_dataset} for the top dataset"
        )
    suggested = suggested[:2]

    return {
        "matched_count": results_count,
        "query_summary": query_summary,
        "suggested_next": suggested,
    }


def build_ai_context_for_datasets() -> Dict:
    """Build _ai_context for dataset list responses."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dataset_entity, COUNT(*) as usage_count
            FROM dataset_usage
            WHERE dataset_entity IS NOT NULL AND dataset_entity != ''
            GROUP BY dataset_entity
            ORDER BY usage_count DESC
            LIMIT 10
        """)
        top = [{"entity": row[0], "usage_count": row[1]} for row in cursor.fetchall()]
        return {"top_datasets": top}
    finally:
        return_db_connection(conn)
