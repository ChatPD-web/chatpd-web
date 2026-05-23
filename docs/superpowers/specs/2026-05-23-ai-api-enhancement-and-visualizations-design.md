# ChatPD AI API Enhancement & Visualizations

## Summary

Three modules:
1. Enrich API responses with `_ai_context` for AI agent efficiency
2. Dataset co-usage force-directed graph (Connected Papers style)
3. Dataset detail page with trend chart + task distribution chart

---

## Module 1: API Response Enhancement

`_ai_context` is included in all entity and query responses (dataset detail, paper detail, query results, dataset list). The two new utility endpoints (`/related`, `/trends`) return purpose-specific JSON shapes and do not include `_ai_context`.

### Affected endpoints with `_ai_context` shape

#### `GET /api/dataset/{name}`

```json
{
  "_ai_context": {
    "entity": "ImageNet",
    "total_papers": 8421,
    "trend": "stable_growth",
    "trend_detail": "Growing 12% per year over the last 3 years",
    "peak_year": 2024,
    "peak_year_count": 2340,
    "top_tasks": [
      {"task": "Image Classification", "count": 4562},
      {"task": "Object Detection", "count": 1890},
      {"task": "Semantic Segmentation", "count": 856},
      {"task": "Fine-Grained Image Classification", "count": 423},
      {"task": "Transfer Learning", "count": 312}
    ],
    "most_related_datasets": [
      {"entity": "COCO", "co_usage_count": 1234},
      {"entity": "CIFAR-10", "co_usage_count": 891},
      {"entity": "CIFAR-100", "co_usage_count": 567},
      {"entity": "Pascal VOC", "co_usage_count": 445},
      {"entity": "MNIST", "co_usage_count": 334}
    ]
  },
  // ... existing response fields unchanged
}
```

**Trend classification algorithm:**
- Compute linear regression slope over the last 3 complete years of usage data
- `"rising"`: slope > +10% per year
- `"stable_growth"`: slope between 0 and +10%
- `"stable"`: slope exactly 0 (no change in 3 years)
- `"declining"`: slope < 0

**`peak_year`**: Calendar year with the highest `COUNT(DISTINCT arxiv_id)`.

**SQL for `top_tasks`**:
```sql
SELECT task, COUNT(DISTINCT arxiv_id) as count
FROM dataset_usage
WHERE dataset_entity = ? AND task IS NOT NULL AND task != ''
GROUP BY task ORDER BY count DESC LIMIT 5
```

**`most_related_datasets`**: Reuse the `/related` endpoint query, limited to top 5.

#### `GET /api/paper/{id}`

```json
{
  "_ai_context": {
    "arxiv_id": "2301.12345",
    "paper_title": "A Novel Approach to Visual Recognition",
    "dataset_count": 5,
    "dataset_entities": ["ImageNet", "COCO", "CIFAR-10", "CIFAR-100", "Places365"],
    "unique_tasks": ["Image Classification", "Object Detection"],
    "unique_data_types": ["RGB Images", "Natural Images"]
  },
  // ... existing response fields
}
```

No new SQL needed — all data already available from existing `get_records_by_arxiv_id()`.

#### `GET /api/query`

```json
{
  "_ai_context": {
    "matched_count": 2341,
    "query_summary": "Found 2,341 records matching 'diffusion model' across 892 datasets and 1,456 papers",
    "suggested_next": [
      "Refine: add task=Image Generation to narrow results",
      "Explore: GET /api/dataset/LAION-5B for the top dataset in these results"
    ]
  },
  // ... existing response fields
}
```

**`query_summary`**: Template-based — "Found {total} records matching '{q}' across {dataset_count} datasets and {paper_count} papers." `suggested_next` is generated from the top task/dataset in results, max 2 suggestions.

#### `GET /api/datasets`

```json
{
  "_ai_context": {
    "top_datasets": [
      {"entity": "ImageNet", "usage_count": 8421},
      // ... top 10
    ]
  },
  // ... existing response fields
}
```

### New endpoints

| Endpoint | Purpose | Cache |
|----------|---------|-------|
| `GET /api/dataset/{name}/related?top_n=20` | Co-used datasets with `co_usage_count` | `@lru_cache(maxsize=256)` |
| `GET /api/dataset/{name}/trends` | Year-by-year usage data | `@lru_cache(maxsize=256)` |

Both endpoints use `@lru_cache` following the existing pattern in `search_engine.py` (line 164-167). The existing `ensure_cache_fresh()` function will be extended to call `.cache_clear()` on these new cached functions when DB mtime changes, ensuring stale data is never served after a DB rebuild.

#### `GET /api/dataset/{name}/related?top_n=20`

Response:
```json
{
  "dataset_entity": "ImageNet",
  "related": [
    {"entity": "COCO", "co_usage_count": 1234},
    {"entity": "CIFAR-10", "co_usage_count": 891}
  ],
  "total_related": 30421
}
```

SQL:
```sql
SELECT d2.dataset_entity, COUNT(DISTINCT d1.arxiv_id) as co_usage_count
FROM dataset_usage d1
JOIN dataset_usage d2 ON d1.arxiv_id = d2.arxiv_id
WHERE d1.dataset_entity = ?
  AND d2.dataset_entity != ?
  AND d2.dataset_entity IS NOT NULL AND d2.dataset_entity != ''
GROUP BY d2.dataset_entity
ORDER BY co_usage_count DESC LIMIT ?
```

Error: Returns 404 `{"error": "Dataset not found"}` if dataset_entity has zero records.

#### `GET /api/dataset/{name}/trends`

Response (monthly granularity, frontend aggregates by year for the chart):
```json
{
  "dataset_entity": "ImageNet",
  "trends": [
    {"year_month": "2001", "paper_count": 5},
    {"year_month": "2002", "paper_count": 8},
    {"year_month": "2506", "paper_count": 423}
  ],
  "yearly_summary": [
    {"year": 2020, "paper_count": 1200},
    {"year": 2021, "paper_count": 1450},
    {"year": 2022, "paper_count": 1680},
    {"year": 2023, "paper_count": 2100},
    {"year": 2024, "paper_count": 2340}
  ]
}
```

SQL for monthly data:
```sql
SELECT SUBSTR(arxiv_id, 1, 2) || SUBSTR(arxiv_id, 3, 2) AS year_month,
       COUNT(DISTINCT arxiv_id) as paper_count
FROM dataset_usage
WHERE dataset_entity = ?
  AND arxiv_id GLOB '[0-9][0-9][0-9][0-9].[0-9]*'
GROUP BY year_month ORDER BY year_month
```

The `yearly_summary` is computed in Python by aggregating the monthly data.

**Note on pre-existing issue**: The `arxiv_yymm_key` column referenced in `query_service.py`'s `ARXIV_YYMM_SQL` constant may be absent from existing DB files built from earlier schema versions (it is defined in `json2db.py` DDL but not present in older deployed DBs). The `create_indexes()` function in `search_engine.py` will silently fail on `idx_arxiv_yymm_key` for these DBs. This is a pre-existing bug — not introduced by this spec. The `SUBSTR` approach above works correctly without the column. A future schema migration could add the computed column and index to improve trend query performance.

---

## Module 2: Dataset Co-usage Graph

### Backend

Uses endpoints from Module 1:
- `GET /api/dataset/{name}/related?top_n=20`
- `GET /api/dataset/{name}/trends`

### Frontend: `dataset_graph.html`

New page at route `/dataset/<dataset_entity>/graph`. Linked from the dataset detail page.

Flask route (in `search_engine.py`):
```python
@app.route("/dataset/<dataset_entity>/graph")
def dataset_graph(dataset_entity):
    return render_template("dataset_graph.html")
```

### D3.js Force Graph

- Center node: target dataset (larger radius, distinct color)
- Satellite nodes: related datasets (radius proportional to `sqrt(co_usage_count)`)
- Edges: only center→satellite (star topology, not full mesh). Stroke width proportional to `co_usage_count`
- Color: center = `#4f46e5`, satellites = `#7c3aed`, edges = `#cbd5e1`

### Interactions

- Hover node → tooltip with entity name + co_usage_count + paper_count
- Click satellite node → navigate to `/dataset/{name}/graph`
- Drag nodes (limited — center node stays near center with stronger force)
- Pinch-to-zoom and pan

### States

| State | Display |
|-------|---------|
| Loading | Spinner + "Loading co-usage data..." |
| Empty (0 related) | "No co-used datasets found for {name}" |
| Error (API fail) | "Failed to load graph data. [Retry]" |
| Success | Force graph rendered |

D3 force config: `.force('charge', d3.forceManyBody().strength(-300))`, `.force('center', d3.forceCenter(width/2, height/2))`, `.force('collision', d3.forceCollide().radius(d => d.radius + 10))`.

---

## Module 3: Dataset Detail Page Charts

Enhance existing `dataset.html`.

### Backend

No new endpoints. Uses existing `GET /api/dataset/{name}` (includes `_ai_context.top_tasks` and `.trend`) plus `GET /api/dataset/{name}/trends`.

### Frontend

Two chart canvases inserted above the usage records table:

**1. Trend line chart** (Chart.js `line`)
- Data: `yearly_summary` from `/trends` endpoint
- X axis: year (integer)
- Y axis: paper count
- Styling: line color `#4f46e5`, fill below line with 10% opacity, no gridlines

**2. Task distribution doughnut chart** (Chart.js `doughnut`)
- Data: `top_tasks` from `_ai_context`
- Slices colored with a 5-color palette
- Legend on the right
- "Other" slice for remaining tasks if total > 5

Both charts wrapped in `<div class="chart-container">` with max-width 600px, centered. Charts are loaded only when the dataset detail page loads — Chart.js is a lazy `<script>` tag.

### Loading states

| State | Display |
|-------|---------|
| Loading | Skeleton placeholder (gray rectangle matching chart dimensions) |
| Error | "Chart unavailable" text, no blank canvas |
| Success | Chart rendered |

---

## Architecture

No infrastructure changes:
- Flask routes in `search_engine.py`: add 2 API routes + 1 page route + modify 4 routes
- Query logic in `query_service.py`: add `get_related_datasets()`, `get_dataset_trends()`, `build_ai_context_for_dataset()`, `build_ai_context_for_paper()`, `build_ai_context_for_query()`, `build_ai_context_for_datasets()`
- Frontend: 1 new HTML page (`dataset_graph.html`), modify `dataset.html`
- D3.js v7 + Chart.js v4 from CDN, lazy-loaded

### Caching

Follow existing pattern: `@lru_cache(maxsize=256)` on `get_related_datasets()` and `get_dataset_trends()`. Cache cleared in `ensure_cache_fresh()` when DB mtime changes.

---

## File changes

| File | Change |
|------|--------|
| `src/web_app/query_service.py` | Add `get_related_datasets()`, `get_dataset_trends()`, 4x `build_ai_context_*()` |
| `src/web_app/search_engine.py` | Add `/api/dataset/<name>/related`, `/api/dataset/<name>/trends` API routes; add `/dataset/<name>/graph` page route; modify 4 routes to add `_ai_context` |
| `dataset.html` | Add chart canvases, lazy Chart.js CDN script, JS to fetch trends + render charts |
| `dataset_graph.html` | New file — D3 force graph with full UI states |
| `static/css/styles.css` | Add `.chart-container`, `.graph-container`, `.tooltip`, skeleton loading styles |
| `llms.txt` | Update with `/related`, `/trends`, `/graph` endpoints |

---

## Non-goals

- No MCP server (future consideration)
- No real-time updates
- No user accounts or personalization
- No complex data processing pipeline changes
- No new database schema or migrations
