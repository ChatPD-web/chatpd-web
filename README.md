# TLDR

## Database Info

```sql
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
```

## License

Dataset Entity Database: https://github.com/paperswithcode/paperswithcode-data (CC-BY-SA 4.0)

## Data Refresh

- Default import source: `data/final_product/ChatPD_WebData_from_db.json`
- Rebuild SQLite data from the default source:

```bash
python3 -m src.json2db
```

- Optional custom source:

```bash
CHATPD_JSON_FILE=data/final_product/ChatPD_WebData.json python3 -m src.json2db
```

- Optional import tuning for large JSON files:

```bash
CHATPD_BATCH_SIZE=2000 CHATPD_COMMIT_EVERY=20000 python3 -m src.json2db
```

- What `src/json2db.py` does:
  - Stream reads the top-level JSON array to avoid loading the full file in memory
  - Rebuilds `data/chatpd_data.db` and recreates table `dataset_usage`
  - Upserts rows by primary key `(arxiv_id, dataset_name)` via `REPLACE INTO`
  - Precomputes `arxiv_time_key` / `arxiv_yymm_key` for faster `latest/earliest` sorting and YYMM filtering

- After rebuilding DB, restart backend service (Gunicorn/systemd) so API reads latest data.

- Check latest data status in running service:
  - API: `GET /api/data-status`
  - Home page: data status panel (record count, dataset count, JSON/DB update time, file size)

## Backend Structure

- `src/web_app/search_engine.py`: Flask app entry, page routes, existing API routes
- `src/web_app/query_service.py`: 独立查询服务层（统一查询、按 arXiv ID 查询）
- `src/json2db.py`: JSON -> SQLite 数据导入脚本
- `docs/architecture.md`: 项目架构文档（系统结构、数据流、API 约定、演进建议）

## Query APIs (Updated)

- `GET /api/query`
  - Primary query endpoint used by frontend
  - Params:
    - `q` (关键词，可空)
    - `field` (`all|arxiv_id|title|dataset_name|dataset_entity|task|data_type`)
    - `match_mode` (`contains|exact|prefix`)
    - `logic` (`and|or`)：多条件组合逻辑
    - `conditions` (JSON 数组字符串)：高级检索规则，元素格式 `{field, value, match_mode}`
    - `sort_by` (`latest|earliest|title|arxiv_id|dataset_name|dataset_entity|task|data_type|scale|location`)
    - `sort_order` (`asc|desc`)
    - `include_stats` (`true|false`)：返回 task/data_type 命中分布（默认 `true`）
    - `page`, `per_page`
  - Response extras:
    - `per_page`, `returned_count`
    - `query_meta.include_stats`

- `GET /api/search`
  - Backward-compatible simple wrapper (internally reuses query service)
  - Params:
    - `keywords`
    - `data_type`, `task`
    - `sort_by`, `sort_order`
    - `include_stats`
    - `page`, `per_page`

- `GET /api/paper/<arxiv_id>`
  - 返回指定论文对应的全部数据集使用记录
  - 新增 `summary` 字段（数据集数、任务数、数据类型数等）

- `GET /api/dataset/<dataset_entity>`
  - 返回数据集详情、使用记录
  - 新增 `summary` 字段（论文数、任务数、数据类型数、地域数等）
