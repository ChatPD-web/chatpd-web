# 🚀 快速部署自动监控系统

## 一键部署（推荐）

```bash
cd /root/web_app/web_chatpd
sudo ./setup_monitoring.sh
```

按照提示操作即可完成：
- ✅ 安装 systemd 服务
- ✅ 配置定时健康检查（推荐每5分钟）
- ✅ 自动切换到 Gunicorn 生产服务器

## 验证部署

```bash
# 1. 检查服务状态
./start_chatpd.sh status

# 2. 查看 Gunicorn 进程（应该有多个 worker）
ps aux | grep gunicorn

# 3. 查看定时任务
crontab -l

# 4. 测试健康检查
./health_check.sh
```

## 日常管理

```bash
# 重启服务
./start_chatpd.sh restart

# 查看日志
tail -f logs/app.log              # 应用日志
tail -f logs/health_check.log     # 健康检查日志

# 查看状态
./start_chatpd.sh status
```

## 问题说明

**为什么会卡死？**
- 之前使用 Flask 开发服务器（单线程）
- Debug 模式导致内存泄漏
- 长时间运行后无法响应请求

**现在的解决方案：**
- ✅ Gunicorn 多进程架构
- ✅ 自动健康检查和重启
- ✅ 生产级稳定性

详细文档：查看 `MONITORING_README.md`

