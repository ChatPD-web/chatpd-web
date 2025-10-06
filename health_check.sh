#!/bin/bash

# ChatPD 健康检查脚本
# 检查服务是否正常响应，如果无响应则自动重启

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
PROJECT_DIR="/root/web_app/web_chatpd"
LOG_FILE="/root/web_app/web_chatpd/logs/health_check.log"
PID_FILE="/root/web_app/web_chatpd/logs/chatpd.pid"
API_URL="https://localhost:5000/api/filters"
MAX_LOG_SIZE=10485760  # 10MB

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error_log() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

success_log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS: $1${NC}" | tee -a "$LOG_FILE"
}

# 日志轮转
rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || stat -f%z "$LOG_FILE" 2>/dev/null)
        if [ "$LOG_SIZE" -gt "$MAX_LOG_SIZE" ]; then
            mv "$LOG_FILE" "$LOG_FILE.$(date +%Y%m%d-%H%M%S)"
            log "日志文件已轮转"
            # 只保留最近10个日志文件
            ls -t "$PROJECT_DIR/logs/health_check.log."* 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null
        fi
    fi
}

# 检查进程是否存在
check_process() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0  # 进程存在
        fi
    fi
    return 1  # 进程不存在
}

# 检查API是否响应
check_api() {
    # 设置5秒超时
    RESPONSE=$(curl -k -s -w "%{http_code}" -o /dev/null --connect-timeout 5 --max-time 10 "$API_URL" 2>/dev/null)
    
    if [ "$RESPONSE" = "200" ]; then
        return 0  # API正常
    else
        return 1  # API异常
    fi
}

# 重启服务
restart_service() {
    error_log "服务无响应，正在重启..."
    cd "$PROJECT_DIR" || exit 1
    
    # 使用启动脚本重启
    if [ -f "$PROJECT_DIR/start_chatpd.sh" ]; then
        bash "$PROJECT_DIR/start_chatpd.sh" restart >> "$LOG_FILE" 2>&1
        
        # 等待服务启动
        sleep 5
        
        # 验证重启是否成功
        if check_api; then
            success_log "服务重启成功！"
            # 发送通知（可选）
            # notify_admin "ChatPD服务已自动重启"
            return 0
        else
            error_log "服务重启后仍然无法响应！"
            return 1
        fi
    else
        error_log "找不到启动脚本: $PROJECT_DIR/start_chatpd.sh"
        return 1
    fi
}

# 发送通知（可扩展）
notify_admin() {
    # 这里可以添加邮件、webhook等通知方式
    # 例如：
    # echo "$1" | mail -s "ChatPD Alert" admin@example.com
    # curl -X POST -H 'Content-type: application/json' --data "{\"text\":\"$1\"}" YOUR_WEBHOOK_URL
    log "通知: $1"
}

# 主检查逻辑
main() {
    rotate_log
    
    # 检查进程
    if ! check_process; then
        error_log "服务进程不存在！"
        restart_service
        exit $?
    fi
    
    # 检查API响应
    if ! check_api; then
        error_log "API无响应（可能卡死）"
        restart_service
        exit $?
    fi
    
    # 一切正常
    log "健康检查通过 ✓"
    return 0
}

# 运行主逻辑
main

exit $?

