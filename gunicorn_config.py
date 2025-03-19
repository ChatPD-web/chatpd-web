import multiprocessing
import os

# 从环境变量读取敏感配置
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# 日志配置
log_dir = os.getenv("LOG_DIR", "logs")
accesslog = f"{log_dir}/access.log"
errorlog = f"{log_dir}/error.log"
loglevel = os.getenv("LOG_LEVEL", "info")

# SSL配置
certfile = os.getenv("SSL_CERT_PATH", "/etc/letsencrypt/live/testweb.241814.xyz/fullchain.pem")
keyfile = os.getenv("SSL_KEY_PATH", "/etc/letsencrypt/live/testweb.241814.xyz/privkey.pem") 