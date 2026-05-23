# AI API Enhancement and Visualizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `_ai_context` to API responses, a D3 dataset co-usage graph, and Chart.js trend/task charts to the ChatPD web project.

**Architecture:** Add helper functions in `query_service.py`, new API routes in `search_engine.py`, two new HTML pages, and charts in existing `dataset.html`. No infrastructure changes — all new JS loaded from CDN.

**Tech Stack:** Python 3.10 / Flask / SQLite / D3.js v7 / Chart.js v4

**Spec:** `docs/superpowers/specs/2026-05-23-ai-api-enhancement-and-visualizations-design.md`

---

### Task 1: Add `get_related_datasets()` to query_service.py

**Files:**
- Modify: `src/web_app/query_service.py` (append to end of file)

- [ ] **Step 1: Add the function**

Add at the end of `src/web_app/query_service.py`:

```python
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

        # Remap dataset_entity → entity for spec compliance
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
```

- [ ] **Step 2: Manual test via Python REPL**

```bash
cd /home/ubuntu/xaj/Program/web_chatpd/web_chatpd
python3 -c "
from src.web_app.query_service import get_related_datasets
r = get_related_datasets('ImageNet', 5)
print('total_related:', r['total_related'])
print('top related:', len(r['related']))
assert r['dataset_entity'] == 'ImageNet'
assert len(r['related']) <= 5
assert r['total_related'] > 0
print('OK')
"
```
Expected: prints OK with meaningful counts.

- [ ] **Step 3: Commit**

```bash
git add src/web_app/query_service.py
git commit -m "feat: add get_related_datasets() for dataset co-usage queries"
```

---

### Task 2: Add `get_dataset_trends()` to query_service.py

**Files:**
- Modify: `src/web_app/query_service.py` (append after Task 1 function)

- [ ] **Step 1: Add the function**

```python
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
            ym = str(m['year_month'])
            if len(ym) == 4:
                year = 2000 + int(ym[:2])
                yearly[year] = yearly.get(year, 0) + m['paper_count']

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
```

- [ ] **Step 2: Manual test**

```bash
cd /home/ubuntu/xaj/Program/web_chatpd/web_chatpd
python3 -c "
from src.web_app.query_service import get_dataset_trends
r = get_dataset_trends('ImageNet')
print('monthly points:', len(r['trends']))
print('yearly points:', len(r['yearly_summary']))
assert len(r['trends']) > 0
assert len(r['yearly_summary']) > 0
assert 'year' in r['yearly_summary'][0]
print('OK')
"
```
Expected: OK with reasonable counts.

- [ ] **Step 3: Commit**

```bash
git add src/web_app/query_service.py
git commit -m "feat: add get_dataset_trends() for usage trend data"
```

---

### Task 3: Add `_ai_context` builder functions to query_service.py

**Files:**
- Modify: `src/web_app/query_service.py` (append after Task 2)

- [ ] **Step 1: Add `build_ai_context_for_dataset()`**

```python
def build_ai_context_for_dataset(dataset_entity: str, records: List[Dict]) -> Dict:
    """Build _ai_context for dataset detail responses."""
    arxiv_ids = set(r['arxiv_id'] for r in records if r.get('arxiv_id'))
    total_papers = len(arxiv_ids)

    task_counts = {}
    for r in records:
        task = r.get('task')
        if task:
            task_counts[task] = task_counts.get(task, 0) + 1

    top_tasks = sorted(task_counts.items(), key=lambda x: -x[1])[:5]

    related_raw = get_related_datasets(dataset_entity, 5)
    most_related = [
        {"entity": rel['dataset_entity'], "co_usage_count": rel['co_usage_count']}
        for rel in related_raw['related']
    ]

    trends_data = get_dataset_trends(dataset_entity)
    yearly = trends_data.get('yearly_summary', [])
    peak_year = None
    peak_count = 0
    if yearly:
        peak = max(yearly, key=lambda y: y['paper_count'])
        peak_year = peak['year']
        peak_count = peak['paper_count']

    trend = "stable"
    trend_detail = "No significant change in the last 3 years"
    if len(yearly) >= 3:
        recent = yearly[-3:]
        n = len(recent)
        xs = list(range(n))
        ys = [y['paper_count'] for y in recent]
        mean_y = sum(ys) / n
        # Linear regression slope as percentage of mean
        num = sum((xs[i] - (n-1)/2) * (ys[i] - mean_y) for i in range(n))
        den = sum((xs[i] - (n-1)/2) ** 2 for i in range(n))
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
        trend_detail = f"{direction} {abs(round(slope_pct))}% per year over the last {n} years"

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
```

- [ ] **Step 2: Add remaining builder functions**

```python
def build_ai_context_for_paper(records: List[Dict]) -> Dict:
    """Build _ai_context for paper detail responses."""
    datasets = sorted(set(
        r.get('dataset_entity') for r in records
        if r.get('dataset_entity')
    ))
    tasks = sorted(set(
        r.get('task') for r in records if r.get('task')
    ))
    data_types = sorted(set(
        r.get('data_type') for r in records if r.get('data_type')
    ))
    arxiv_id = records[0].get('arxiv_id') if records else None
    title = records[0].get('title') if records else None
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
    task_counts = {}
    for r in results:
        if r.get('dataset_entity'):
            datasets.add(r['dataset_entity'])
            if top_dataset is None:
                top_dataset = r['dataset_entity']
        if r.get('arxiv_id'):
            papers.add(r['arxiv_id'])
        task = r.get('task')
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
        suggested.append(
            f"Refine: add task={top_task} to narrow results"
        )
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
```

- [ ] **Step 3: Manual test**

```bash
cd /home/ubuntu/xaj/Program/web_chatpd/web_chatpd
python3 -c "
from src.web_app.query_service import (
    build_ai_context_for_dataset, build_ai_context_for_paper,
    build_ai_context_for_query, build_ai_context_for_datasets,
    get_records_by_arxiv_id, search_records, get_dataset_details
)
# Test dataset context
import sys; sys.path.insert(0, 'src/web_app')
from search_engine import get_dataset_details
details = get_dataset_details('ImageNet')
ctx = build_ai_context_for_dataset('ImageNet', details)
print('Dataset context:', ctx['trend'], ctx['total_papers'], 'papers')

# Test query context
results = search_records(q='diffusion', per_page=5)
ctx2 = build_ai_context_for_query(results['results_count'], 'diffusion', results['results'])
print('Query context:', ctx2['query_summary'][:80])

# Test datasets context
ctx3 = build_ai_context_for_datasets()
print('Datasets context: top', len(ctx3['top_datasets']))
print('OK')
"
```
Expected: prints OK with context data.

- [ ] **Step 4: Commit**

```bash
git add src/web_app/query_service.py
git commit -m "feat: add _ai_context builder functions for all endpoints"
```

---

### Task 4: Add new API routes to search_engine.py

**Files:**
- Modify: `src/web_app/search_engine.py`

- [ ] **Step 1: Import new functions**

At the top of `search_engine.py`, add to the existing `from .query_service import` line:

```python
from .query_service import (
    QUERY_LOGIC_MODES,
    QUERYABLE_FIELDS,
    QUERY_MATCH_MODES,
    SORTABLE_FIELDS,
    get_records_by_arxiv_id,
    search_records,
    get_related_datasets,
    get_dataset_trends,
    build_ai_context_for_dataset,
    build_ai_context_for_paper,
    build_ai_context_for_query,
    build_ai_context_for_datasets,
)
```

- [ ] **Step 2: Add `/api/dataset/<name>/related` route**

Add before the `if __name__` block (around line 853):

```python
@app.route("/api/dataset/<dataset_entity>/related", methods=["GET"])
def dataset_related_api(dataset_entity):
    """Return datasets co-used with the given dataset."""
    try:
        top_n = min(int(request.args.get("top_n", 20)), 50)
        result = get_related_datasets(dataset_entity, top_n)
        if not result["related"]:
            details = get_dataset_details(dataset_entity)
            if not details:
                return json_response({"error": "Dataset not found"}, 404)
        return json_response(result)
    except Exception as e:
        app.logger.error(f"Dataset related API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)


@app.route("/api/dataset/<dataset_entity>/trends", methods=["GET"])
def dataset_trends_api(dataset_entity):
    """Return monthly and yearly usage trends for a dataset."""
    try:
        result = get_dataset_trends(dataset_entity)
        if not result["trends"]:
            return json_response({"error": "Dataset not found"}, 404)
        return json_response(result)
    except Exception as e:
        app.logger.error(f"Dataset trends API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)
```

- [ ] **Step 3: Modify `/api/dataset/<name>` route to include `_ai_context`**

In the `dataset_detail_api` function (around line 760), before the return statement, add `_ai_context`:

```python
    ai_context = build_ai_context_for_dataset(dataset_entity, details)
    return (
        json.dumps(
            {
                "dataset": details[0],
                "usage_records": details,
                "_ai_context": ai_context,
                "summary": { ... },
            },
            ensure_ascii=False,
        ),
        200,
        {"Content-Type": "application/json"},
    )
```

- [ ] **Step 4: Modify `/api/paper/<id>` route to include `_ai_context`**

In `paper_detail_api` (around line 667), add:

```python
    ai_context = build_ai_context_for_paper(records)
    return json_response(
        {
            "arxiv_id": arxiv_id,
            "count": len(records),
            "paper_title": paper_title,
            "_ai_context": ai_context,
            "summary": { ... },
            "records": records,
        }
    )
```

- [ ] **Step 5: Modify `/api/query` and `/api/search` routes**

For **`search_api`** (around line 516), capture the response and add `_ai_context`:

```python
    response = search_records(
        q=keywords,
        field="all",
        match_mode="contains",
        ...
    )
    if include_stats or request.args.get("include_ai_context", "true").lower() in {"1", "true", "yes", "on"}:
        ai_context = build_ai_context_for_query(
            response["results_count"],
            keywords or "",
            response["results"][:20],
        )
        response["_ai_context"] = ai_context
    response["query_meta"]["api_mode"] = "simple_compat"
    return json_response(response)
```

For **`unified_query_api`** (around line 643), restructure to capture the response:

```python
    try:
        response = search_records(
            q=q,
            field=field,
            ...
        )
        if include_stats or request.args.get("include_ai_context", "true").lower() in {"1", "true", "yes", "on"}:
            ai_context = build_ai_context_for_query(
                response["results_count"],
                q or "",
                response["results"][:20],
            )
            response["_ai_context"] = ai_context
        return json_response(response)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except Exception as e:
        app.logger.error(f"Unified query API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)
```

- [ ] **Step 6: Modify `/api/datasets` route**

In `datasets_api` (around line 705), add before the return:

```python
    ai_context = build_ai_context_for_datasets()
    return (
        json.dumps({
            "datasets": datasets,
            "total_count": total_count,
            "total_pages": ceil(total_count / per_page),
            "current_page": page,
            "_ai_context": ai_context,
        }, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )
```

- [ ] **Step 7: Expand `ensure_cache_fresh()`**

In `ensure_cache_fresh()` (around line 226), add after existing cache clears:

```python
        if current_mtime != cached_db_mtime:
            get_top_data_types_cached.cache_clear()
            get_top_tasks_cached.cache_clear()
            get_related_datasets.cache_clear()
            get_dataset_trends.cache_clear()
            cached_db_mtime = current_mtime
```

Add `@lru_cache` decorators to the new functions in `query_service.py`:

```python
from functools import lru_cache

@lru_cache(maxsize=256)
def get_related_datasets(dataset_entity: str, top_n: int = 20) -> Dict:
    ...

@lru_cache(maxsize=256)
def get_dataset_trends(dataset_entity: str) -> Dict:
    ...
```

- [ ] **Step 8: Manual test via curl**

```bash
cd /home/ubuntu/xaj/Program/web_chatpd/web_chatpd
# Start Flask dev server in background
FLASK_ENV=development python3 -m src.web_app.search_engine &
sleep 3

# Test new endpoints
curl -s http://127.0.0.1:5000/api/dataset/ImageNet/related?top_n=3 | python3 -m json.tool | head -10
curl -s http://127.0.0.1:5000/api/dataset/ImageNet/trends | python3 -m json.tool | head -10

# Test _ai_context in existing endpoints
curl -s http://127.0.0.1:5000/api/dataset/ImageNet | python3 -c "import sys,json; d=json.load(sys.stdin); print('_ai_context' in d, d.get('_ai_context',{}).get('trend'))"
curl -s http://127.0.0.1:5000/api/query?q=diffusion\&per_page=3 | python3 -c "import sys,json; d=json.load(sys.stdin); print('_ai_context' in d, d['_ai_context']['query_summary'][:60])"

# Stop Flask
kill %1
```

- [ ] **Step 9: Commit**

```bash
git add src/web_app/search_engine.py src/web_app/query_service.py
git commit -m "feat: add /related and /trends API routes + _ai_context in all responses"
```

---

### Task 5: Add graph page route and HTML

**Files:**
- Modify: `src/web_app/search_engine.py` (add page route)
- Create: `dataset_graph.html`

- [ ] **Step 1: Add Flask route for graph page**

In `search_engine.py`, add before the `if __name__` block (near the other page routes around line 848):

```python
@app.route("/dataset/<dataset_entity>/graph")
def dataset_graph(dataset_entity):
    """Display the dataset co-usage force-directed graph."""
    return render_template("dataset_graph.html")
```

- [ ] **Step 2: Create `dataset_graph.html`**

Create the HTML file with D3 force graph. The page should:
- Load D3.js v7 from CDN
- Read `dataset_entity` from the URL path
- Fetch `/api/dataset/{name}/related?top_n=20` and `/api/dataset/{name}/trends`
- Render a force-directed graph (star topology: center node = target, satellites = related)
- Show loading spinner, error state, empty state
- Support click-to-navigate to related dataset graphs
- Have tooltips on hover

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dataset Graph - ChatPD</title>
    <link id="css-link" rel="stylesheet" href="static/css/styles.css">
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        .graph-container { width: 100%; height: 80vh; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; position: relative; }
        .graph-tooltip { position: absolute; padding: 8px 12px; background: rgba(0,0,0,0.85); color: white; border-radius: 6px; font-size: 13px; pointer-events: none; opacity: 0; transition: opacity 0.15s; z-index: 10; }
        .graph-loading, .graph-error, .graph-empty { display: flex; align-items: center; justify-content: center; height: 60vh; font-size: 16px; color: #64748b; }
        .graph-error button { margin-left: 12px; padding: 6px 16px; background: #4f46e5; color: white; border: none; border-radius: 4px; cursor: pointer; }
        .graph-header { margin-bottom: 16px; }
        .graph-header h2 { margin: 0; font-size: 22px; }
        .graph-legend { display: flex; gap: 16px; margin-top: 8px; font-size: 13px; color: #64748b; }
        .graph-legend span { display: flex; align-items: center; gap: 4px; }
        .legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
        .graph-stats { display: flex; gap: 24px; margin-top: 8px; }
        .graph-stat { font-size: 14px; color: #475569; }
        .graph-stat strong { color: #1e293b; }
    </style>
</head>
<body>
    <nav class="top-nav">
        <ul>
            <li><a href="./">Home</a></li>
            <li><a href="datasets">Datasets</a></li>
            <li><a href="api.html">API</a></li>
        </ul>
    </nav>

    <div class="container">
        <div class="graph-header">
            <h2 id="graph-title">Dataset Co-usage Graph</h2>
            <p class="subtitle" id="graph-subtitle">Loading...</p>
            <div class="graph-legend">
                <span><span class="legend-dot" style="background:#4f46e5"></span> Target dataset</span>
                <span><span class="legend-dot" style="background:#7c3aed"></span> Related datasets</span>
                <span>Edge thickness = co-usage count</span>
            </div>
            <div class="graph-stats" id="graph-stats"></div>
        </div>

        <div id="graph-loading" class="graph-loading">Loading co-usage data...</div>
        <div id="graph-error" class="graph-error" style="display:none">
            Failed to load graph data. <button onclick="location.reload()">Retry</button>
        </div>
        <div id="graph-empty" class="graph-empty" style="display:none">No co-used datasets found.</div>
        <div class="graph-container" id="graph-container" style="display:none"></div>
        <div class="graph-tooltip" id="graph-tooltip"></div>
    </div>

    <script>
    (function() {
        const path = window.location.pathname;
        const parts = path.split('/').filter(Boolean);
        const datasetEntity = decodeURIComponent(parts[parts.length - 1]);

        document.getElementById('graph-subtitle').textContent = datasetEntity;

        const container = document.getElementById('graph-container');
        const tooltip = document.getElementById('graph-tooltip');
        const loadingEl = document.getElementById('graph-loading');
        const errorEl = document.getElementById('graph-error');
        const emptyEl = document.getElementById('graph-empty');
        const statsEl = document.getElementById('graph-stats');

        function getApiUrl() {
            const hostname = window.location.hostname;
            if (hostname === 'chatpd-web.github.io' || hostname.includes('github.io')) {
                return 'https://testweb.241814.xyz/chatpd';
            }
            if (hostname === 'localhost' || hostname === '127.0.0.1') {
                return '';
            }
            return 'https://testweb.241814.xyz/chatpd';
        }

        const apiUrl = getApiUrl();

        Promise.all([
            fetch(`${apiUrl}/api/dataset/${encodeURIComponent(datasetEntity)}/related?top_n=20`).then(r => r.json()),
            fetch(`${apiUrl}/api/dataset/${encodeURIComponent(datasetEntity)}/trends`).then(r => r.json())
        ]).then(([relatedData, trendsData]) => {
            if (relatedData.error) throw new Error(relatedData.error);
            if (!relatedData.related || relatedData.related.length === 0) {
                loadingEl.style.display = 'none';
                emptyEl.style.display = 'flex';
                document.getElementById('graph-subtitle').textContent =
                    datasetEntity + ' — no co-used datasets found';
                return;
            }

            loadingEl.style.display = 'none';
            container.style.display = 'block';

            const yearly = trendsData.yearly_summary || [];
            const totalPapers = yearly.reduce((s, y) => s + y.paper_count, 0);
            statsEl.innerHTML = `
                <div class="graph-stat">Related datasets: <strong>${relatedData.total_related}</strong></div>
                <div class="graph-stat">Total papers: <strong>${totalPapers.toLocaleString()}</strong></div>
            `;

            const nodes = [
                {
                    id: datasetEntity,
                    isCenter: true,
                    radius: 28,
                    co_usage_count: relatedData.total_related || 0
                },
                ...relatedData.related.map(r => ({
                    id: r.dataset_entity,
                    isCenter: false,
                    radius: Math.max(8, Math.sqrt(r.co_usage_count) * 0.8),
                    co_usage_count: r.co_usage_count
                }))
            ];

            const links = relatedData.related.map(r => ({
                source: datasetEntity,
                target: r.dataset_entity,
                value: r.co_usage_count
            }));

            const width = container.clientWidth;
            const height = container.clientHeight || Math.max(500, window.innerHeight * 0.7);
            container.style.height = height + 'px';

            const svg = d3.select('#graph-container')
                .append('svg')
                .attr('width', width)
                .attr('height', height);

            const g = svg.append('g');

            const zoom = d3.zoom()
                .scaleExtent([0.3, 4])
                .on('zoom', (event) => g.attr('transform', event.transform));
            svg.call(zoom);

            const simulation = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(links).id(d => d.id).distance(120))
                .force('charge', d3.forceManyBody().strength(-300))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('collision', d3.forceCollide().radius(d => d.radius + 8));

            const link = g.append('g')
                .selectAll('line')
                .data(links)
                .join('line')
                .attr('stroke', '#cbd5e1')
                .attr('stroke-width', d => Math.max(1, Math.sqrt(d.value) * 0.3))
                .attr('stroke-opacity', 0.6);

            const node = g.append('g')
                .selectAll('g')
                .data(nodes)
                .join('g')
                .call(d3.drag()
                    .on('start', (event, d) => {
                        if (!event.active) simulation.alphaTarget(0.3).restart();
                        d.fx = d.x; d.fy = d.y;
                    })
                    .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
                    .on('end', (event, d) => {
                        if (!event.active) simulation.alphaTarget(0);
                        if (!d.isCenter) { d.fx = null; d.fy = null; }
                    })
                );

            node.append('circle')
                .attr('r', d => d.radius)
                .attr('fill', d => d.isCenter ? '#4f46e5' : '#7c3aed')
                .attr('opacity', d => d.isCenter ? 1 : 0.7)
                .attr('stroke', d => d.isCenter ? '#3730a3' : '#5b21b6')
                .attr('stroke-width', d => d.isCenter ? 3 : 1)
                .on('mouseenter', (event, d) => {
                    tooltip.style('opacity', 1)
                        .html(`<strong>${d.id}</strong><br>Co-usage: ${d.co_usage_count.toLocaleString()}`)
                        .style('left', (event.pageX + 12) + 'px')
                        .style('top', (event.pageY - 28) + 'px');
                })
                .on('mouseleave', () => tooltip.style('opacity', 0))
                .on('click', (event, d) => {
                    if (!d.isCenter) {
                        window.location.href =
                            `${path.split('/').slice(0, -1).join('/')}/${encodeURIComponent(d.id)}/graph`;
                    }
                })
                .style('cursor', d => d.isCenter ? 'default' : 'pointer');

            node.append('text')
                .text(d => d.id.length > 18 ? d.id.slice(0, 17) + '...' : d.id)
                .attr('text-anchor', 'middle')
                .attr('dy', d => d.radius + 14)
                .attr('font-size', d => d.isCenter ? 13 : 11)
                .attr('fill', '#334155');

            simulation.on('tick', () => {
                link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
                node.attr('transform', d => `translate(${d.x},${d.y})`);
            });

            // Pin center node
            const centerNode = nodes[0];
            centerNode.fx = width / 2;
            centerNode.fy = height / 2;
        }).catch(err => {
            console.error(err);
            loadingEl.style.display = 'none';
            errorEl.style.display = 'flex';
        });
    })();
    </script>
</body>
</html>
```

- [ ] **Step 3: Manual test**

```bash
cd /home/ubuntu/xaj/Program/web_chatpd/web_chatpd
FLASK_ENV=development python3 -m src.web_app.search_engine &
sleep 3
# Test the graph page loads
curl -s http://127.0.0.1:5000/dataset/ImageNet/graph | grep -c "d3js.org" 
# Expected: 1 (D3 CDN script tag found)
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add dataset_graph.html src/web_app/search_engine.py
git commit -m "feat: add D3 dataset co-usage graph page"
```

---

### Task 6: Enhance dataset.html with Chart.js charts

**Files:**
- Modify: `dataset.html`

- [ ] **Step 1: Add graph page link**

In `dataset.html`, add a navigation link to the graph page near the dataset header/summary section:

```html
<a id="graph-link" href="#" class="graph-nav-link">View Co-usage Graph →</a>
```

The JS should dynamically set the href:

```javascript
const graphLink = document.getElementById('graph-link');
if (graphLink) {
    const datasetEntity = /* extract from URL */;
    graphLink.href = `./${encodeURIComponent(datasetEntity)}/graph`;
}
```

Add CSS style for the link:

```css
.graph-nav-link {
    display: inline-block;
    padding: 6px 16px;
    background: #4f46e5;
    color: white;
    text-decoration: none;
    border-radius: 6px;
    font-size: 14px;
    margin: 8px 0 16px;
}
.graph-nav-link:hover { background: #3730a3; }
```

- [ ] **Step 2: Add chart canvases and Chart.js CDN**

In `dataset.html`, add chart containers before the usage records section. Add Chart.js CDN at the bottom. The JS should:
- Extract dataset_entity from the URL path
- Fetch `/api/dataset/{name}/trends` for the line chart
- Fetch `/api/dataset/{name}` for the doughnut chart data (from `_ai_context.top_tasks`)
- Render both charts

```html
<!-- Add in <head> or before </body>: -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
    .chart-container { max-width: 600px; margin: 24px auto; }
    .chart-container h3 { margin-bottom: 12px; font-size: 16px; color: #1e293b; }
    .chart-wrapper { position: relative; height: 300px; }
    .chart-skeleton { height: 300px; background: #f1f5f9; border-radius: 8px; animation: pulse 1.5s infinite; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
</style>

<!-- Add in body, before the records table: -->
<div class="chart-container" id="trend-chart-container">
    <h3>Usage Trends</h3>
    <div class="chart-wrapper">
        <canvas id="trend-chart"></canvas>
    </div>
    <div class="chart-skeleton" id="trend-skeleton"></div>
</div>

<div class="chart-container" id="task-chart-container">
    <h3>Task Distribution</h3>
    <div class="chart-wrapper">
        <canvas id="task-chart"></canvas>
    </div>
    <div class="chart-skeleton" id="task-skeleton"></div>
</div>
```

- [ ] **Step 2: Add chart rendering JS**

Add at the end of `dataset.html` (before `</body>`):

```html
<script>
(function() {
    const path = window.location.pathname;
    const parts = path.split('/').filter(Boolean);
    const datasetEntity = decodeURIComponent(parts[parts.length - 1]);

    function getApiUrl() {
        const hostname = window.location.hostname;
        if (hostname === 'chatpd-web.github.io' || hostname.includes('github.io')) {
            return 'https://testweb.241814.xyz/chatpd';
        }
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return '';
        }
        return 'https://testweb.241814.xyz/chatpd';
    }

    const apiUrl = getApiUrl();

    // Trend chart
    fetch(`${apiUrl}/api/dataset/${encodeURIComponent(datasetEntity)}/trends`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('trend-skeleton').style.display = 'none';
            if (!data.yearly_summary || data.yearly_summary.length === 0) {
                document.getElementById('trend-chart-container').innerHTML =
                    '<p style="color:#94a3b8">No trend data available.</p>';
                return;
            }
            const ctx = document.getElementById('trend-chart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.yearly_summary.map(d => d.year),
                    datasets: [{
                        label: 'Papers',
                        data: data.yearly_summary.map(d => d.paper_count),
                        borderColor: '#4f46e5',
                        backgroundColor: 'rgba(79,70,229,0.08)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 3,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { title: { display: true, text: 'Year' }, grid: { display: false } },
                        y: { title: { display: true, text: 'Paper Count' }, beginAtZero: true }
                    }
                }
            });
        })
        .catch(() => {
            document.getElementById('trend-chart-container').innerHTML =
                '<p style="color:#94a3b8">Chart unavailable.</p>';
        });

    // Task distribution chart
    fetch(`${apiUrl}/api/dataset/${encodeURIComponent(datasetEntity)}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('task-skeleton').style.display = 'none';
            const tasks = data._ai_context?.top_tasks || [];
            if (tasks.length === 0) {
                document.getElementById('task-chart-container').innerHTML =
                    '<p style="color:#94a3b8">No task data available.</p>';
                return;
            }
            const colors = ['#4f46e5', '#7c3aed', '#a78bfa', '#c4b5fd', '#e0e7ff'];
            const ctx = document.getElementById('task-chart').getContext('2d');
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: tasks.map(t => t.task),
                    datasets: [{
                        data: tasks.map(t => t.count),
                        backgroundColor: colors.slice(0, tasks.length),
                        borderColor: '#ffffff',
                        borderWidth: 2,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: { padding: 16, font: { size: 12 } }
                        }
                    }
                }
            });
        })
        .catch(() => {
            document.getElementById('task-chart-container').innerHTML =
                '<p style="color:#94a3b8">Chart unavailable.</p>';
        });
})();
</script>
```

- [ ] **Step 3: Manual test**

```bash
cd /home/ubuntu/xaj/Program/web_chatpd/web_chatpd
FLASK_ENV=development python3 -m src.web_app.search_engine &
sleep 3
# Check chart containers in HTML
curl -s http://127.0.0.1:5000/dataset/ImageNet | grep -c "trend-chart\|task-chart\|Chart.js"
# Expected: at least 3 matches (canvas elements + CDN link)
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add dataset.html
git commit -m "feat: add Chart.js trend line and task doughnut to dataset page"
```

---

### Task 7: Add CSS styles and update llms.txt

**Files:**
- Modify: `static/css/styles.css`
- Modify: `llms.txt`

- [ ] **Step 1: Add CSS styles**

Append to `static/css/styles.css`:

```css
/* Graph page */
.graph-container svg { display: block; }
.graph-tooltip { pointer-events: none; }

/* Chart containers */
.chart-container h3 { margin-bottom: 12px; font-size: 16px; color: #1e293b; }
.chart-wrapper { position: relative; height: 300px; }
.chart-skeleton { height: 300px; background: #f1f5f9; border-radius: 8px; animation: chart-pulse 1.5s ease-in-out infinite; }
@keyframes chart-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.graph-stats { display: flex; gap: 24px; margin-top: 8px; }
.graph-stat { font-size: 14px; color: #475569; }
.graph-stat strong { color: #1e293b; }
```

- [ ] **Step 2: Update llms.txt**

Add to the `## Key API endpoints` section:

```
- `GET /api/dataset/<entity>/related?top_n=20` — datasets co-used with this one
- `GET /api/dataset/<entity>/trends` — monthly and yearly usage trends
```

Add to the `## Example requests` section:

```
GET https://testweb.241814.xyz/chatpd/api/dataset/ImageNet/related?top_n=10
GET https://testweb.241814.xyz/chatpd/api/dataset/ImageNet/trends
```

Add to the `## Pages` section:

```
- https://chatpd-web.github.io/chatpd-web/dataset/ImageNet/graph — co-usage graph visualization
```

- [ ] **Step 3: Commit**

```bash
git add static/css/styles.css llms.txt
git commit -m "feat: add graph/chart styles and update llms.txt with new endpoints"
```

---

### Task 8: Local integration test

- [ ] **Step 1: Full integration test**

```bash
cd /home/ubuntu/xaj/Program/web_chatpd/web_chatpd
FLASK_ENV=development python3 -m src.web_app.search_engine &
sleep 4

echo "=== Test 1: data-status ==="
curl -s http://127.0.0.1:5000/api/data-status | python3 -c "import sys,json; d=json.load(sys.stdin); print('Records:', d['total_records'])"

echo "=== Test 2: dataset _ai_context ==="
curl -s http://127.0.0.1:5000/api/dataset/ImageNet | python3 -c "import sys,json; d=json.load(sys.stdin); ctx=d.get('_ai_context',{}); print('trend:', ctx.get('trend'), 'papers:', ctx.get('total_papers'))"

echo "=== Test 3: related ==="
curl -s http://127.0.0.1:5000/api/dataset/ImageNet/related?top_n=3 | python3 -c "import sys,json; d=json.load(sys.stdin); print('related count:', len(d['related']), 'total:', d['total_related'])"

echo "=== Test 4: trends ==="
curl -s http://127.0.0.1:5000/api/dataset/ImageNet/trends | python3 -c "import sys,json; d=json.load(sys.stdin); print('monthly pts:', len(d['trends']), 'yearly pts:', len(d['yearly_summary']))"

echo "=== Test 5: query _ai_context ==="
curl -s "http://127.0.0.1:5000/api/query?q=diffusion&per_page=3" | python3 -c "import sys,json; d=json.load(sys.stdin); ctx=d.get('_ai_context',{}); print('summary:', ctx.get('query_summary','N/A')[:80])"

echo "=== Test 6: paper _ai_context ==="
curl -s http://127.0.0.1:5000/api/paper/2301.12345 | python3 -c "import sys,json; d=json.load(sys.stdin); ctx=d.get('_ai_context',{}); print('datasets:', ctx.get('dataset_count','N/A'))"

echo "=== Test 7: graph page ==="
curl -s http://127.0.0.1:5000/dataset/ImageNet/graph | grep -c "d3js.org" | xargs echo "D3 loaded:"

echo "=== Test 8: dataset page charts ==="
curl -s http://127.0.0.1:5000/dataset/ImageNet | grep -c "Chart.js\|trend-chart\|task-chart" | xargs echo "Chart refs:"

kill %1
echo "=== All tests complete ==="
```
Expected: All tests pass with meaningful data values.

- [ ] **Step 2: Commit any final fixes**

---

### Task 9: Deploy to server

- [ ] **Step 1: Copy updated files to server**

```bash
scp src/web_app/query_service.py xaj@150.109.111.210:~/Deployment/src/web_app/
scp src/web_app/search_engine.py xaj@150.109.111.210:~/Deployment/src/web_app/
scp dataset.html xaj@150.109.111.210:~/Deployment/
scp dataset_graph.html xaj@150.109.111.210:~/Deployment/
scp static/css/styles.css xaj@150.109.111.210:~/Deployment/static/css/
scp llms.txt xaj@150.109.111.210:~/Deployment/
```

- [ ] **Step 2: Restart service and verify**

```bash
ssh xaj@150.109.111.210 'echo "111111ajAJ" | sudo -S systemctl restart chatpd 2>&1'
sleep 8

# Verify HTTPS endpoints
curl -sk https://testweb.241814.xyz/chatpd/api/dataset/ImageNet/related?top_n=3 | python3 -c "import sys,json; d=json.load(sys.stdin); print('related:', len(d['related']))"
curl -sk https://testweb.241814.xyz/chatpd/api/dataset/ImageNet/trends | python3 -c "import sys,json; d=json.load(sys.stdin); print('trends yearly:', len(d['yearly_summary']))"
curl -sk https://testweb.241814.xyz/chatpd/api/dataset/ImageNet | python3 -c "import sys,json; d=json.load(sys.stdin); print('_ai_context:', d.get('_ai_context',{}).get('trend','MISSING'))"
curl -sk https://testweb.241814.xyz/chatpd/dataset/ImageNet/graph | grep -c "d3js.org" | xargs echo "Graph page D3:"
```

All commands should return success.

- [ ] **Step 3: Push to GitHub (for GitHub Pages)**

```bash
git push origin main
```

- [ ] **Step 4: Commit**

Final commit if any deployment adjustments were needed.
