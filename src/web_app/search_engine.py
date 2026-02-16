import json
import re
from flask import Flask, request, render_template, jsonify
from collections import Counter
from math import ceil
from flask_cors import CORS
import sqlite3
import os
import threading
from functools import lru_cache
import time
from datetime import datetime
from .config import (
    SSL_CERT_PATH, SSL_KEY_PATH, SERVER_ADDRESS, SERVER_PORT,
    ENV, SERVER_URL
)
from .query_service import (
    QUERYABLE_FIELDS,
    QUERY_MATCH_MODES,
    get_records_by_arxiv_id,
    search_records,
)

# 数据库连接池
class DatabasePool:
    def __init__(self, db_path, max_connections=10):
        self.db_path = db_path
        self.max_connections = max_connections
        self.connections = []
        self.lock = threading.Lock()
        
    def get_connection(self):
        with self.lock:
            if self.connections:
                return self.connections.pop()
            else:
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                # 启用WAL模式提高并发性能
                conn.execute('PRAGMA journal_mode=WAL;')
                # 启用查询优化
                conn.execute('PRAGMA optimize;')
                return conn
    
    def return_connection(self, conn):
        with self.lock:
            if len(self.connections) < self.max_connections:
                self.connections.append(conn)
            else:
                conn.close()

# 全局路径与连接池
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_SOURCE_JSON = os.path.join(PROJECT_ROOT, "data/final_product/ChatPD_WebData_from_db.json")
db_path = os.path.join(PROJECT_ROOT, "data/chatpd_data.db")
db_pool = DatabasePool(db_path)
cache_state_lock = threading.Lock()
cached_db_mtime = None

# 创建数据库索引
def create_indexes():
    """创建数据库索引以提高查询性能"""
    conn = db_pool.get_connection()
    try:
        cursor = conn.cursor()
        # 为常用查询字段创建索引
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_data_type ON dataset_usage(data_type);",
            "CREATE INDEX IF NOT EXISTS idx_task ON dataset_usage(task);",
            "CREATE INDEX IF NOT EXISTS idx_dataset_entity ON dataset_usage(dataset_entity);",
            "CREATE INDEX IF NOT EXISTS idx_arxiv_id ON dataset_usage(arxiv_id);",
            "CREATE INDEX IF NOT EXISTS idx_title ON dataset_usage(title);",
            "CREATE INDEX IF NOT EXISTS idx_dataset_name ON dataset_usage(dataset_name);",
            # 复合索引for常见查询组合
            "CREATE INDEX IF NOT EXISTS idx_data_type_task ON dataset_usage(data_type, task);",
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        conn.commit()
    finally:
        db_pool.return_connection(conn)

# 在应用启动时创建索引
create_indexes()

# 连接SQLite数据库 - 使用连接池
def get_db_connection():
    """
    从连接池获取数据库连接
    """
    return db_pool.get_connection()

def return_db_connection(conn):
    """
    将连接返回到连接池
    """
    db_pool.return_connection(conn)


def format_timestamp(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def get_data_status():
    """返回当前系统数据源与数据库状态，用于前端展示“最新数据”信息。"""
    source_exists = os.path.exists(DATA_SOURCE_JSON)
    db_exists = os.path.exists(db_path)

    status = {
        "source_json_path": DATA_SOURCE_JSON,
        "source_json_exists": source_exists,
        "source_json_size_bytes": os.path.getsize(DATA_SOURCE_JSON) if source_exists else 0,
        "source_json_mtime": format_timestamp(os.path.getmtime(DATA_SOURCE_JSON)) if source_exists else None,
        "database_path": db_path,
        "database_exists": db_exists,
        "database_size_bytes": os.path.getsize(db_path) if db_exists else 0,
        "database_mtime": format_timestamp(os.path.getmtime(db_path)) if db_exists else None,
        "total_records": 0,
        "total_datasets": 0,
    }

    if not db_exists:
        return status

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM dataset_usage")
        status["total_records"] = cursor.fetchone()["count"]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT dataset_entity) AS count
            FROM dataset_usage
            WHERE dataset_entity IS NOT NULL AND dataset_entity != ""
            """
        )
        status["total_datasets"] = cursor.fetchone()["count"]
    finally:
        return_db_connection(conn)

    return status

# 获取所有数据
def get_all_data():
    """
    从数据库中获取所有数据
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dataset_usage')
    data = [dict(row) for row in cursor.fetchall()]
    return_db_connection(conn)
    return data


# 缓存装饰器用于热点数据
@lru_cache(maxsize=128, typed=True)
def get_top_data_types_cached(top_n=15):
    """
    获取出现次数最多的 N 种 data type (带缓存)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT data_type, COUNT(*) as count 
            FROM dataset_usage 
            WHERE data_type IS NOT NULL AND data_type != "" 
            GROUP BY data_type 
            ORDER BY count DESC
            LIMIT ?
        ''', (top_n,))
        data_types = cursor.fetchall()
        return [(dt['data_type'], dt['count']) for dt in data_types]
    finally:
        return_db_connection(conn)

@lru_cache(maxsize=128, typed=True)
def get_top_tasks_cached(top_n=15):
    """
    获取出现次数最多的 N 种 task (带缓存)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT task, COUNT(*) as count 
            FROM dataset_usage 
            WHERE task IS NOT NULL AND task != "" 
            GROUP BY task 
            ORDER BY count DESC
            LIMIT ?
        ''', (top_n,))
        tasks = cursor.fetchall()
        return [(t['task'], t['count']) for t in tasks]
    finally:
        return_db_connection(conn)

# 统计 data type 的出现次数
def get_top_data_types(top_n=15):
    """
    获取出现次数最多的 N 种 data type
    """
    ensure_cache_fresh()
    return get_top_data_types_cached(top_n)

# 统计 task 的出现次数
def get_top_tasks(top_n=15):
    """
    获取出现次数最多的 N 种 task
    """
    ensure_cache_fresh()
    return get_top_tasks_cached(top_n)


def ensure_cache_fresh():
    """
    当数据库文件发生变化时，清理与统计相关的缓存，确保返回最新数据。
    """
    global cached_db_mtime

    if not os.path.exists(db_path):
        return

    current_mtime = os.path.getmtime(db_path)
    with cache_state_lock:
        if cached_db_mtime is None:
            cached_db_mtime = current_mtime
            return

        if current_mtime != cached_db_mtime:
            get_top_data_types_cached.cache_clear()
            get_top_tasks_cached.cache_clear()
            cached_db_mtime = current_mtime


# 获取数据集列表
def get_datasets():
    """
    获取所有不同的数据集及其使用次数
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT dataset_entity, COUNT(*) as usage_count 
        FROM dataset_usage 
        WHERE dataset_entity IS NOT NULL AND dataset_entity != "" 
        GROUP BY dataset_entity 
        ORDER BY usage_count DESC
    ''')
    datasets = [dict(row) for row in cursor.fetchall()]
    return_db_connection(conn)
    return datasets


# 获取特定数据集的详细信息
def get_dataset_details(dataset_entity):
    """
    获取特定数据集的所有使用记录
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
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
                dataset_name, dataset_summary, task, data_type, location, scale,
                dataset_citation, dataset_provider, dataset_url, dataset_publicly_available,
                other_info, entity_name, dataset_entity, papers_with_code_url, homepage
            FROM dataset_usage 
            WHERE dataset_entity = ?
        ''', (dataset_entity,))
        records = [dict(row) for row in cursor.fetchall()]
        return records
    finally:
        return_db_connection(conn)


# 优化的数据过滤逻辑
def filter_data(data_type=None, task=None, keywords=None, page=1, per_page=10):
    """
    根据 data type、task 和关键词过滤数据
    :param data_type: 数据类型（如 Graph、Text 等）
    :param task: 任务类型（如 Classification）
    :param keywords: 搜索关键词（字符串）
    :param page: 当前页码
    :param per_page: 每页条数
    :return: 过滤后的数据和总页数
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 构建查询条件
        conditions = []
        params = []
        
        if data_type and data_type != "All":
            conditions.append("data_type = ?")
            params.append(data_type)
            
        if task and task != "All":
            conditions.append("task = ?")
            params.append(task)
            
        if keywords and keywords.strip():
            # 优化的搜索逻辑 - 使用更高效的查询
            search_term = f"%{keywords.strip()}%"
            # 使用UNION和优先级搜索，提高相关性
            keywords_condition = """(
                arxiv_id LIKE ? OR
                title LIKE ? OR 
                dataset_name LIKE ? OR
                dataset_entity LIKE ? OR
                dataset_summary LIKE ? OR
                task LIKE ? OR
                data_type LIKE ?
            )"""
            conditions.append(keywords_condition)
            params.extend([search_term] * 7)
        
        # 组装完整查询
        base_query = "FROM dataset_usage"
        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
        
        # 获取总记录数 - 使用更高效的COUNT查询
        count_query = f"SELECT COUNT(*) as count {base_query}{where_clause}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()["count"]
        total_pages = ceil(total_count / per_page)
        
        # 主查询 - 只获取需要的字段，并处理空标题
        select_fields = """
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
        
        query = f"SELECT {select_fields} {base_query}{where_clause}"
        
        # 添加排序和分页
        query += " ORDER BY "
        if keywords and keywords.strip():
            # 关键词搜索时按相关性排序
            query += """
                CASE 
                    WHEN arxiv_id LIKE ? THEN 1
                    WHEN title LIKE ? THEN 2
                    WHEN dataset_name LIKE ? THEN 3
                    WHEN dataset_entity LIKE ? THEN 4
                    ELSE 5
                END,
                title LIMIT ? OFFSET ?
            """
            relevance_params = [f"%{keywords.strip()}%"] * 4
            params.extend(relevance_params)
        else:
            # 默认按标题排序
            query += "title LIMIT ? OFFSET ?"
        
        offset = (page - 1) * per_page
        params.extend([per_page, offset])
        
        # 执行查询
        cursor.execute(query, params)
        filtered_data = [dict(row) for row in cursor.fetchall()]
        
        return filtered_data, total_count, total_pages
    finally:
        return_db_connection(conn)


# 分页逻辑
def get_pagination(current_page, total_pages, delta=2):
    """
    生成分页按钮的显示范围
    :param current_page: 当前页
    :param total_pages: 总页数
    :param delta: 当前页前后显示的页数范围
    :return: 分页按钮列表（包括省略号）
    """
    if total_pages <= 1:
        return []

    pagination = []
    if current_page > 1:
        pagination.append(1)  # 首页
    if current_page > delta + 2:
        pagination.append("...")  # 左侧省略号

    for i in range(
        max(1, current_page - delta), min(total_pages + 1, current_page + delta + 1)
    ):
        pagination.append(i)

    if current_page < total_pages - delta - 1:
        pagination.append("...")  # 右侧省略号
    if current_page < total_pages:
        pagination.append(total_pages)  # 尾页

    return pagination


# Flask 应用
app = Flask(__name__, 
    static_folder="../../static",  # 静态文件路径
    template_folder="../..",       # 模板文件路径
    static_url_path="/static"      # 静态文件URL路径
)
CORS(app, resources={r"/*": {"origins": "*"}})

# 添加调试模式
app.debug = True

# 启用响应压缩
from flask import g
import gzip
import io

@app.after_request
def after_request(response):
    # 启用gzip压缩，但跳过静态文件和流式响应
    try:
        # 检查是否是静态文件请求
        if (request.endpoint == 'static' or 
            request.path.startswith('/static/') or
            response.status_code < 200 or 
            response.status_code >= 300 or 
            'Content-Encoding' in response.headers or
            response.direct_passthrough):
            return response
        
        # 只压缩JSON和HTML响应
        if (response.content_type and 
            (response.content_type.startswith('application/json') or 
             response.content_type.startswith('text/html'))):
            accept_encoding = request.headers.get('Accept-Encoding', '')
            if 'gzip' in accept_encoding.lower():
                data = response.get_data()
                if data:
                    response.data = gzip.compress(data)
                    response.headers['Content-Encoding'] = 'gzip'
                    response.headers['Content-Length'] = len(response.data)
    except Exception as e:
        # 如果压缩失败，返回原始响应
        app.logger.warning(f"Compression failed: {e}")
        pass
    
    return response

# 优化的JSON响应函数
def json_response(data, status_code=200):
    """优化的JSON响应，减少序列化开销"""
    return jsonify(data), status_code

# 确保静态文件可以被访问
@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)

@app.route("/api/search", methods=["GET"])
def search_api():
    try:
        keywords = request.args.get("keywords", "").strip()
        data_type = request.args.get("data_type", "All")
        task = request.args.get("task", "All")
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(int(request.args.get("per_page", 10)), 50)  # 限制最大页面大小

        filtered_data, results_count, total_pages = filter_data(data_type, task, keywords, page, per_page)

        response = {
            "results": filtered_data,
            "results_count": results_count,
            "total_pages": total_pages,
            "current_page": page
        }
        return json_response(response)
    except Exception as e:
        app.logger.error(f"Search API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)

@app.route("/api/filters", methods=["GET"])
def filters_api():
    try:
        top_data_types = get_top_data_types()
        top_tasks = get_top_tasks()

        # 将元组转换为字典列表
        top_data_types_list = [{"data_type": dt, "count": c} for dt, c in top_data_types]
        top_tasks_list = [{"task": t, "count": c} for t, c in top_tasks]

        response = {"top_data_types": top_data_types_list, "top_tasks": top_tasks_list}
        return json_response(response)
    except Exception as e:
        app.logger.error(f"Filters API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)


@app.route("/api/data-status", methods=["GET"])
def data_status_api():
    try:
        return json_response(get_data_status())
    except Exception as e:
        app.logger.error(f"Data status API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)


@app.route("/api/query", methods=["GET"])
def unified_query_api():
    """
    统一基础查询接口，支持：
    - q: 关键词
    - field: all/arxiv_id/title/dataset_name/dataset_entity/task/data_type
    - match_mode: contains/exact/prefix
    - page/per_page: 分页参数
    """
    q = request.args.get("q", "").strip()
    field = request.args.get("field", "all").strip()
    match_mode = request.args.get("match_mode", "contains").strip()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(int(request.args.get("per_page", 10)), 50)

    if field not in QUERYABLE_FIELDS:
        return json_response(
            {
                "error": "Invalid field",
                "allowed_fields": sorted(list(QUERYABLE_FIELDS.keys())),
            },
            400,
        )
    if match_mode not in QUERY_MATCH_MODES:
        return json_response(
            {
                "error": "Invalid match_mode",
                "allowed_match_modes": sorted(list(QUERY_MATCH_MODES)),
            },
            400,
        )

    try:
        return json_response(search_records(q, field, match_mode, page, per_page))
    except Exception as e:
        app.logger.error(f"Unified query API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)


@app.route("/api/paper/<arxiv_id>", methods=["GET"])
def paper_detail_api(arxiv_id):
    """按 arXiv ID 查询论文关联的数据集记录。"""
    try:
        records = get_records_by_arxiv_id(arxiv_id)
        return json_response(
            {
                "arxiv_id": arxiv_id,
                "count": len(records),
                "records": records,
            }
        )
    except Exception as e:
        app.logger.error(f"Paper detail API error: {str(e)}")
        return json_response({"error": "Internal server error"}, 500)

@app.route("/api/datasets", methods=["GET"])
def datasets_api():
    """获取所有数据集列表，支持分页"""
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    search = request.args.get("search", "").strip()
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 添加搜索条件
    search_condition = ""
    params = []
    
    if search:
        search_condition = "AND dataset_entity LIKE ?"
        params.append(f"%{search}%")
    
    # 获取总记录数
    cursor.execute(f'''
        SELECT COUNT(DISTINCT dataset_entity) as total 
        FROM dataset_usage 
        WHERE dataset_entity IS NOT NULL AND dataset_entity != "" {search_condition}
    ''', params)
    total_count = cursor.fetchone()["total"]
    
    # 获取分页数据
    query = f'''
        SELECT dataset_entity, COUNT(*) as usage_count 
        FROM dataset_usage 
        WHERE dataset_entity IS NOT NULL AND dataset_entity != "" {search_condition}
        GROUP BY dataset_entity 
        ORDER BY usage_count DESC
        LIMIT ? OFFSET ?
    '''
    
    cursor.execute(query, params + [per_page, offset])
    
    datasets = [dict(row) for row in cursor.fetchall()]
    return_db_connection(conn)
    
    return (
        json.dumps({
            "datasets": datasets,
            "total_count": total_count,
            "total_pages": ceil(total_count / per_page),
            "current_page": page
        }, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/dataset/<dataset_entity>", methods=["GET"])
def dataset_detail_api(dataset_entity):
    """获取特定数据集的详细信息"""
    details = get_dataset_details(dataset_entity)
    if not details:
        return (
            json.dumps({"error": "Dataset not found"}, ensure_ascii=False),
            404,
            {"Content-Type": "application/json"},
        )
    
    return (
        json.dumps({"dataset": details[0], "usage_records": details}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/")
def home():
    selected_data_type = request.args.get("data_type", "All")
    selected_task = request.args.get("task", "All")
    keywords = request.args.get("keywords", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = 10

    top_data_types = get_top_data_types()
    top_tasks = get_top_tasks()
    filtered_data, results_count, total_pages = filter_data(selected_data_type, selected_task, keywords, page, per_page)

    # 调用分页函数
    pagination = get_pagination(page, total_pages)

    return render_template(
        "index.html",
        results=filtered_data,
        results_count=results_count,
        top_data_types=top_data_types,
        top_tasks=top_tasks,
        selected_data_type=selected_data_type,
        selected_task=selected_task,
        keywords=keywords,
        current_page=page,
        total_pages=total_pages,
        pagination=pagination,
    )


@app.route("/datasets")
def datasets():
    """显示所有数据集列表页面"""
    return render_template("datasets.html")


@app.route("/dataset/<dataset_entity>")
def dataset_detail(dataset_entity):
    """显示特定数据集的详细信息页面"""
    details = get_dataset_details(dataset_entity)
    if not details:
        return "Dataset not found", 404
    
    dataset_info = details[0]
    return render_template("dataset.html", dataset=dataset_info, records=details)


if __name__ == "__main__":
    if ENV == 'production':
        # 生产环境使用SSL
        app.run(
            host=SERVER_ADDRESS,
            port=SERVER_PORT,
            ssl_context=(SSL_CERT_PATH, SSL_KEY_PATH),
        )
    else:
        # 开发环境不使用SSL
        app.run(
            host=SERVER_ADDRESS,
            port=SERVER_PORT,
        )



