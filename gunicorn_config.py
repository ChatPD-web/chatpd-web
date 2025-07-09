import multiprocessing
import os

# 从环境变量读取敏感配置
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")

# 优化worker配置
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)  # 限制最大worker数
worker_class = "gevent"  # 使用异步worker提高并发
worker_connections = 2000  # 增加连接数
timeout = 60  # 增加超时时间
keepalive = 3  # 增加keepalive时间

# 预加载应用以节省内存
preload_app = True

# 内存和性能优化
max_requests = 1000  # 防止内存泄漏
max_requests_jitter = 100
worker_tmp_dir = "/dev/shm"  # 使用内存文件系统

# 日志配置
log_dir = os.getenv("LOG_DIR", "logs")
accesslog = f"{log_dir}/access.log"
errorlog = f"{log_dir}/error.log"
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# SSL配置
certfile = os.getenv("SSL_CERT_PATH", "/etc/letsencrypt/live/testweb.241814.xyz/fullchain.pem")
keyfile = os.getenv("SSL_KEY_PATH", "/etc/letsencrypt/live/testweb.241814.xyz/privkey.pem")

# 性能调优
backlog = 2048  # 增加backlog队列大小

def when_ready(server):
    """服务器准备就绪时的回调"""
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    """worker收到SIGINT信号时的回调"""
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    """fork worker前的回调"""
    server.log.info("Worker spawned (pid: %s)", worker.pid) 