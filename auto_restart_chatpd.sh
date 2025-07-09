#!/bin/bash

# ChatPD 自动重启和健康检查脚本
# 解决长期运行导致的进程僵死问题

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 设置项目路径
PROJECT_DIR="/root/web_app/web_chatpd"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$PROJECT_DIR/logs/chatpd.pid"
HEALTH_LOG="$PROJECT_DIR/logs/health_check.log"
STARTUP_SCRIPT="$PROJECT_DIR/start_chatpd.sh"

# 创建必要目录
mkdir -p "$LOG_DIR"

# 日志函数
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$HEALTH_LOG"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >> "$HEALTH_LOG"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1" >> "$HEALTH_LOG"
}

# 健康检查函数
health_check() {
    local retries=3
    local wait_time=5
    
    for i in $(seq 1 $retries); do
        # 检查进程是否存在
        if [ ! -f "$PID_FILE" ]; then
            error "PID文件不存在"
            return 1
        fi
        
        PID=$(cat "$PID_FILE")
        if ! kill -0 "$PID" 2>/dev/null; then
            error "进程不存在 PID: $PID"
            return 1
        fi
        
        # 检查API响应
        if curl -k -s --connect-timeout 10 --max-time 15 "https://localhost:5000/api/filters" | grep -q "top_data_types"; then
            log "健康检查通过 (尝试 $i/$retries)"
            return 0
        else
            warn "API无响应 (尝试 $i/$retries)"
            if [ $i -lt $retries ]; then
                sleep $wait_time
            fi
        fi
    done
    
    error "健康检查失败，API连续无响应"
    return 1
}

# 检查进程运行时间
check_runtime() {
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    if ! kill -0 "$PID" 2>/dev/null; then
        return 1
    fi
    
    # 获取进程启动时间（秒）
    START_TIME=$(stat -c %Y /proc/$PID 2>/dev/null || echo 0)
    CURRENT_TIME=$(date +%s)
    RUNTIME=$((CURRENT_TIME - START_TIME))
    
    # 20小时 = 72000秒
    if [ $RUNTIME -gt 72000 ]; then
        warn "进程运行时间过长: $((RUNTIME/3600))小时"
        return 1
    fi
    
    return 0
}

# 检查系统资源
check_resources() {
    # 检查内存使用率
    MEMORY_USAGE=$(free | grep Mem | awk '{printf("%.0f", $3/$2 * 100.0)}')
    if [ "$MEMORY_USAGE" -gt 85 ]; then
        warn "内存使用率过高: ${MEMORY_USAGE}%"
        return 1
    fi
    
    # 检查磁盘使用率
    DISK_USAGE=$(df /root | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$DISK_USAGE" -gt 90 ]; then
        warn "磁盘使用率过高: ${DISK_USAGE}%"
        return 1
    fi
    
    return 0
}

# 重启服务
restart_service() {
    log "开始重启ChatPD服务..."
    cd "$PROJECT_DIR" || exit 1
    
    if "$STARTUP_SCRIPT" restart; then
        log "✅ 服务重启成功"
        
        # 等待服务完全启动
        sleep 10
        
        # 验证重启后的健康状态
        if health_check; then
            log "✅ 重启后健康检查通过"
            return 0
        else
            error "重启后健康检查失败"
            return 1
        fi
    else
        error "服务重启失败"
        return 1
    fi
}

# 主监控逻辑
main_monitor() {
    log "开始ChatPD健康检查..."
    
    local need_restart=false
    
    # 健康检查
    if ! health_check; then
        warn "健康检查失败，需要重启"
        need_restart=true
    fi
    
    # 运行时间检查
    if ! check_runtime; then
        warn "运行时间过长，需要重启"
        need_restart=true
    fi
    
    # 资源检查
    if ! check_resources; then
        warn "系统资源异常，建议重启"
        need_restart=true
    fi
    
    if [ "$need_restart" = true ]; then
        restart_service
    else
        log "✅ 所有检查通过，服务正常"
    fi
}

# 强制重启（定期重启）
force_restart() {
    log "执行定期重启..."
    restart_service
}

# 清理日志
cleanup_logs() {
    # 清理健康检查日志（保留最近1000行）
    if [ -f "$HEALTH_LOG" ] && [ $(wc -l < "$HEALTH_LOG") -gt 1000 ]; then
        tail -1000 "$HEALTH_LOG" > "${HEALTH_LOG}.tmp"
        mv "${HEALTH_LOG}.tmp" "$HEALTH_LOG"
        log "健康检查日志已清理"
    fi
    
    # 清理应用日志
    APP_LOG="$PROJECT_DIR/logs/app.log"
    if [ -f "$APP_LOG" ] && [ $(stat -c%s "$APP_LOG") -gt 10485760 ]; then
        mv "$APP_LOG" "$APP_LOG.old"
        log "应用日志已轮转"
    fi
}

# 命令行参数处理
case "$1" in
    "monitor")
        main_monitor
        ;;
    "force-restart")
        force_restart
        ;;
    "health-check")
        health_check && echo "健康" || echo "异常"
        ;;
    "cleanup")
        cleanup_logs
        ;;
    *)
        echo "ChatPD自动重启脚本"
        echo ""
        echo "用法: $0 {monitor|force-restart|health-check|cleanup}"
        echo ""
        echo "命令说明:"
        echo "  monitor       - 执行健康检查，必要时自动重启"
        echo "  force-restart - 强制重启服务"
        echo "  health-check  - 仅执行健康检查"
        echo "  cleanup       - 清理日志文件"
        echo ""
        echo "建议设置cron任务："
        echo "# 每30分钟检查一次"
        echo "*/30 * * * * $0 monitor"
        echo "# 每天凌晨3点强制重启"
        echo "0 3 * * * $0 force-restart"
        exit 1
        ;;
esac 