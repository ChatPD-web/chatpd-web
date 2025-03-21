import json
import re
from flask import Flask, request, render_template
from collections import Counter
from math import ceil
from flask_cors import CORS
import sqlite3
import os
from .config import (
    SSL_CERT_PATH, SSL_KEY_PATH, SERVER_ADDRESS, SERVER_PORT,
    ENV, SERVER_URL
)


# 连接SQLite数据库
def get_db_connection():
    """
    创建数据库连接
    """
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data/chatpd_data.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 将查询结果转换为类字典对象
    return conn


# 获取所有数据
def get_all_data():
    """
    从数据库中获取所有数据
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dataset_usage')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return data


# 统计 data type 的出现次数
def get_top_data_types(top_n=15):
    """
    获取出现次数最多的 N 种 data type
    """
    conn = get_db_connection()
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
    conn.close()
    return [(dt['data_type'], dt['count']) for dt in data_types]


# 统计 task 的出现次数
def get_top_tasks(top_n=15):
    """
    获取出现次数最多的 N 种 task
    """
    conn = get_db_connection()
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
    conn.close()
    return [(t['task'], t['count']) for t in tasks]


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
    conn.close()
    return datasets


# 获取特定数据集的详细信息
def get_dataset_details(dataset_entity):
    """
    获取特定数据集的所有使用记录
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM dataset_usage 
        WHERE dataset_entity = ?
    ''', (dataset_entity,))
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return records


# 数据过滤逻辑
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
        # SQLite全文搜索（模糊匹配多个字段）
        keywords_condition = " OR ".join([
            f"{col} LIKE ?" for col in [
                "arxiv_id", "title", "dataset_name", "dataset_summary", 
                "task", "data_type", "dataset_entity"
            ]
        ])
        conditions.append(f"({keywords_condition})")
        search_term = f"%{keywords.strip()}%"
        params.extend([search_term] * 7)  # 为每个字段添加相同的搜索词
    
    # 组装完整查询
    query = "SELECT * FROM dataset_usage"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # 获取总记录数
    count_query = f"SELECT COUNT(*) as count FROM ({query})"
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()["count"]
    total_pages = ceil(total_count / per_page)
    
    # 添加分页
    query += " LIMIT ? OFFSET ?"
    offset = (page - 1) * per_page
    params.extend([per_page, offset])
    
    # 执行查询
    cursor.execute(query, params)
    filtered_data = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return filtered_data, total_count, total_pages


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

# 确保静态文件可以被访问
@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)


@app.route("/api/search", methods=["GET"])
def search_api():
    keywords = request.args.get("keywords", "").strip()
    data_type = request.args.get("data_type", "All")
    task = request.args.get("task", "All")
    page = int(request.args.get("page", 1))
    per_page = 10

    filtered_data, results_count, total_pages = filter_data(data_type, task, keywords, page, per_page)

    response = {
        "results": filtered_data,
        "results_count": results_count,
        "total_pages": total_pages,
    }
    return (
        json.dumps(response, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/filters", methods=["GET"])
def filters_api():
    top_data_types = get_top_data_types()
    top_tasks = get_top_tasks()

    # 将元组转换为字典列表
    top_data_types_list = [{"data_type": dt, "count": c} for dt, c in top_data_types]
    top_tasks_list = [{"task": t, "count": c} for t, c in top_tasks]

    response = {"top_data_types": top_data_types_list, "top_tasks": top_tasks_list}
    return (
        json.dumps(response, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )


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
    conn.close()
    
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



