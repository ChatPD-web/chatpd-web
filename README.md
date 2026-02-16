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
    PRIMARY KEY (arxiv_id, dataset_name)
)
```

## License

Dataset Entity Database: https://github.com/paperswithcode/paperswithcode-data (CC-BY-SA 4.0)

## Data Refresh

- Default import source: `data/final_product/ChatPD_WebData_from_db.json`
- Rebuild SQLite data:

```bash
python3 -m src.json2db
```

- Optional custom source:

```bash
CHATPD_JSON_FILE=data/final_product/ChatPD_WebData.json python3 -m src.json2db
```

- Check latest data status in running service:
  - API: `GET /api/data-status`
  - Home page: data status panel (record count, dataset count, JSON/DB update time, file size)

## Backend Structure

- `src/web_app/search_engine.py`: Flask app entry, page routes, existing API routes
- `src/web_app/query_service.py`: 独立查询服务层（统一查询、按 arXiv ID 查询）
- `src/json2db.py`: JSON -> SQLite 数据导入脚本

## Basic Query APIs

- `GET /api/query`
  - Params:
    - `q` (关键词，可空)
    - `field` (`all|arxiv_id|title|dataset_name|dataset_entity|task|data_type`)
    - `match_mode` (`contains|exact|prefix`)
    - `page`, `per_page`
- `GET /api/paper/<arxiv_id>`
  - 返回指定论文对应的全部数据集使用记录
