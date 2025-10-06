# ChatPD 监控和自动重启系统说明

## 📋 问题分析

### 原因诊断
您的服务卡死是因为使用了 **Flask 开发服务器** 而不是生产级 WSGI 服务器：

1. **Flask 开发服务器问题**：
   - 单线程处理请求，无法处理并发
   - Debug 模式导致内存泄漏
   - 长时间运行后容易卡死
   - 官方明确警告：`WARNING: This is a development server. Do not use it in a production deployment.`

2. **实际表现**：
   - 进程存在但无响应
   - API 调用超时
   - 前端无法获取数据

### 解决方案
已切换到 **Gunicorn + gevent** 生产服务器：
- ✅ 多进程架构，避免单点故障
- ✅ 异步 I/O，提高并发能力
- ✅ 自动重启 worker，防止内存泄漏
- ✅ 生产级稳定性

---

## 🚀 已完成的改进

### 1. 切换到 Gunicorn 生产服务器
**改进内容**：
- 修改 `start_chatpd.sh` 使用 Gunicorn 启动
- 配置 8 个 worker 进程（基于 CPU 核心数）
- 使用 gevent 异步 worker 提高性能
- 每个 worker 处理 1000 个请求后自动重启（防止内存泄漏）

**当前状态**：
```bash
$ ps aux | grep gunicorn
root  4035858  /usr/bin/python3 /usr/local/bin/gunicorn  # Master进程
root  4035866  /usr/bin/python3 /usr/local/bin/gunicorn  # Worker 1
root  4035867  /usr/bin/python3 /usr/local/bin/gunicorn  # Worker 2
root  4035868  /usr/bin/python3 /usr/local/bin/gunicorn  # Worker 3
root  4035869  /usr/bin/python3 /usr/local/bin/gunicorn  # Worker 4
root  4035870  /usr/bin/python3 /usr/local/bin/gunicorn  # Worker 5
```

### 2. 健康检查脚本
**脚本路径**：`/root/web_app/web_chatpd/health_check.sh`

**功能**：
- 检查进程是否存在
- 检测 API 是否响应（5秒超时）
- 如果无响应，自动重启服务
- 记录详细日志

**测试**：
```bash
$ ./health_check.sh
[2025-10-06 14:56:05] 健康检查通过 ✓
```

### 3. 自动监控系统配置脚本
**脚本路径**：`/root/web_app/web_chatpd/setup_monitoring.sh`

**功能**：
- 一键配置 systemd 服务
- 设置 cron 定时健康检查
- 测试健康检查功能
- 自动切换到 Gunicorn

---

## 📝 部署监控系统

### 方案一：快速部署（推荐）

运行一键配置脚本：
```bash
cd /root/web_app/web_chatpd
sudo ./setup_monitoring.sh
```

脚本会引导您完成：
1. ✅ 安装 systemd 服务（可选）
2. ✅ 配置定时健康检查
3. ✅ 选择检查频率（推荐：每5分钟）
4. ✅ 测试健康检查
5. ✅ 重启服务使用 Gunicorn

### 方案二：手动配置

#### 步骤 1：配置 cron 定时任务
```bash
# 编辑 crontab
crontab -e

# 添加以下行（每5分钟检查一次）
*/5 * * * * /root/web_app/web_chatpd/health_check.sh > /dev/null 2>&1

# 保存退出，查看确认
crontab -l
```

**检查频率建议**：
- 生产环境：每 5-10 分钟
- 测试环境：每 30 分钟
- 高负载环境：每 2-3 分钟

#### 步骤 2：配置 systemd 服务（可选）
```bash
# 复制服务文件
sudo cp /root/web_app/web_chatpd/chatpd.service /etc/systemd/system/

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用开机自动启动
sudo systemctl enable chatpd

# 启动服务
sudo systemctl start chatpd

# 查看状态
sudo systemctl status chatpd
```

**systemd 优势**：
- 自动重启：服务异常退出时自动重启
- 日志管理：使用 journalctl 统一管理日志
- 资源限制：可配置 CPU、内存限制
- 开机自启：系统重启后自动启动

---

## 🔧 管理命令

### 使用启动脚本（推荐日常使用）
```bash
cd /root/web_app/web_chatpd

# 启动服务
./start_chatpd.sh start

# 停止服务
./start_chatpd.sh stop

# 重启服务
./start_chatpd.sh restart

# 查看状态
./start_chatpd.sh status

# 查看日志
./start_chatpd.sh logs
```

### 使用 systemd（如果已安装）
```bash
# 启动
sudo systemctl start chatpd

# 停止
sudo systemctl stop chatpd

# 重启
sudo systemctl restart chatpd

# 状态
sudo systemctl status chatpd

# 查看日志（实时）
sudo journalctl -u chatpd -f

# 查看最近100行日志
sudo journalctl -u chatpd -n 100
```

### 手动运行健康检查
```bash
cd /root/web_app/web_chatpd
./health_check.sh
```

---

## 📊 日志位置

### 应用日志
```bash
# 应用运行日志
tail -f /root/web_app/web_chatpd/logs/app.log

# Gunicorn 访问日志
tail -f /root/web_app/web_chatpd/logs/access.log

# Gunicorn 错误日志
tail -f /root/web_app/web_chatpd/logs/error.log

# 健康检查日志
tail -f /root/web_app/web_chatpd/logs/health_check.log
```

### systemd 日志（如果使用）
```bash
# 查看服务日志
sudo journalctl -u chatpd

# 实时跟踪日志
sudo journalctl -u chatpd -f

# 查看最近的错误
sudo journalctl -u chatpd -p err

# 查看今天的日志
sudo journalctl -u chatpd --since today
```

---

## 🔍 监控和诊断

### 检查服务健康
```bash
# 方法1：使用启动脚本
./start_chatpd.sh status

# 方法2：手动检查进程
ps aux | grep gunicorn

# 方法3：检查端口
netstat -tlnp | grep 5000

# 方法4：测试 API
curl -k https://localhost:5000/api/filters
```

### 查看 worker 状态
```bash
# 查看所有 Gunicorn 进程
ps aux | grep gunicorn

# 查看进程树
pstree -p $(cat /root/web_app/web_chatpd/logs/chatpd.pid)

# 查看资源使用
top -p $(pgrep -d',' -f gunicorn)
```

### 诊断问题
```bash
# 1. 查看最近的错误日志
tail -100 /root/web_app/web_chatpd/logs/error.log

# 2. 查看健康检查历史
tail -100 /root/web_app/web_chatpd/logs/health_check.log

# 3. 查看系统日志
sudo journalctl -xe

# 4. 检查磁盘空间
df -h

# 5. 检查内存使用
free -h
```

---

## 🚨 告警和通知（可选扩展）

### 集成邮件通知
编辑 `health_check.sh`，在 `notify_admin()` 函数中添加：
```bash
notify_admin() {
    echo "$1" | mail -s "ChatPD Alert" your-email@example.com
}
```

### 集成 Webhook（钉钉、企业微信等）
```bash
notify_admin() {
    curl -X POST -H 'Content-type: application/json' \
         --data "{\"text\":\"$1\"}" \
         YOUR_WEBHOOK_URL
}
```

### 集成监控平台
- Prometheus + Grafana
- Datadog
- New Relic
- 阿里云/腾讯云监控

---

## 📈 性能优化建议

### Gunicorn 配置调优
编辑 `gunicorn_config.py`：

```python
# 根据 CPU 核心数调整 worker 数量
workers = multiprocessing.cpu_count() * 2 + 1

# 增加超时时间（如果有慢查询）
timeout = 120

# 调整连接数
worker_connections = 2000

# 定期重启 worker（防止内存泄漏）
max_requests = 1000
max_requests_jitter = 100
```

### 数据库优化
- 已添加索引（`idx_data_type`, `idx_task` 等）
- 使用连接池
- WAL 模式提高并发

### 缓存优化
- 已使用 `@lru_cache` 缓存热点数据
- 前端使用 5 分钟缓存

---

## ✅ 验证部署

### 1. 确认服务状态
```bash
./start_chatpd.sh status
```
应该显示：
```
✅ 服务正在运行
✅ 端口5000正在监听  
✅ API接口正常响应
🚀 ChatPD服务完全正常！
```

### 2. 确认使用 Gunicorn
```bash
ps aux | grep gunicorn | grep -v grep
```
应该看到多个 gunicorn 进程。

### 3. 确认定时任务
```bash
crontab -l | grep health_check
```
应该看到 cron 任务。

### 4. 确认健康检查工作
```bash
tail -f /root/web_app/web_chatpd/logs/health_check.log
```
等待 5 分钟，应该看到新的检查记录。

### 5. 测试前端访问
访问：https://chatpd-web.github.io/chatpd-web/

应该能正常显示数据。

---

## 🎯 总结

### 问题根源
- ❌ Flask 开发服务器不适合生产环境
- ❌ 单线程处理，容易卡死
- ❌ 缺少监控和自动恢复机制

### 解决方案
- ✅ 切换到 Gunicorn 多进程服务器
- ✅ 实现健康检查和自动重启
- ✅ 提供 systemd 和 cron 两种监控方式
- ✅ 完善日志和诊断工具

### 长期建议
1. 定期查看日志，关注异常
2. 监控系统资源使用
3. 定期备份数据库
4. 考虑使用 Nginx 反向代理
5. 配置告警通知

---

## 📞 支持

如有问题，请查看：
- 应用日志：`/root/web_app/web_chatpd/logs/app.log`
- 健康检查日志：`/root/web_app/web_chatpd/logs/health_check.log`
- 启动脚本：`./start_chatpd.sh status`

**最后更新**：2025-10-06

