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