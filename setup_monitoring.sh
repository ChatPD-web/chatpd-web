#!/bin/bash

# ChatPD 监控系统设置脚本
# 配置systemd服务和定时健康检查

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="/root/web_app/web_chatpd"

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then 
    error "请使用root权限运行此脚本"
    exit 1
fi

echo "=========================================="
echo "  ChatPD 监控系统设置"
echo "=========================================="
echo ""

# 1. 设置systemd服务（可选）
read -p "是否安装systemd服务？(y/n，推荐) [y]: " install_systemd
install_systemd=${install_systemd:-y}

if [ "$install_systemd" = "y" ] || [ "$install_systemd" = "Y" ]; then
    log "安装systemd服务..."
    
    # 复制服务文件
    cp "$PROJECT_DIR/chatpd.service" /etc/systemd/system/
    
    # 重新加载systemd
    systemctl daemon-reload
    
    # 询问是否启用自动启动
    read -p "是否启用开机自动启动？(y/n) [y]: " enable_service
    enable_service=${enable_service:-y}
    
    if [ "$enable_service" = "y" ] || [ "$enable_service" = "Y" ]; then
        systemctl enable chatpd
        log "✅ 已启用开机自动启动"
    fi
    
    info "systemd服务管理命令："
    info "  启动: sudo systemctl start chatpd"
    info "  停止: sudo systemctl stop chatpd"
    info "  重启: sudo systemctl restart chatpd"
    info "  状态: sudo systemctl status chatpd"
    info "  日志: sudo journalctl -u chatpd -f"
    echo ""
else
    log "跳过systemd服务安装"
fi

# 2. 设置cron定时健康检查
read -p "是否设置定时健康检查？(y/n，推荐) [y]: " setup_cron
setup_cron=${setup_cron:-y}

if [ "$setup_cron" = "y" ] || [ "$setup_cron" = "Y" ]; then
    log "设置cron定时任务..."
    
    # 询问检查频率
    echo ""
    echo "选择健康检查频率："
    echo "  1) 每5分钟检查一次（推荐）"
    echo "  2) 每10分钟检查一次"
    echo "  3) 每30分钟检查一次"
    echo "  4) 每小时检查一次"
    read -p "请选择 [1]: " check_freq
    check_freq=${check_freq:-1}
    
    case $check_freq in
        1) CRON_SCHEDULE="*/5 * * * *" ;;
        2) CRON_SCHEDULE="*/10 * * * *" ;;
        3) CRON_SCHEDULE="*/30 * * * *" ;;
        4) CRON_SCHEDULE="0 * * * *" ;;
        *) CRON_SCHEDULE="*/5 * * * *" ;;
    esac
    
    # 创建cron任务
    CRON_CMD="$CRON_SCHEDULE $PROJECT_DIR/health_check.sh > /dev/null 2>&1"
    
    # 检查是否已存在
    if crontab -l 2>/dev/null | grep -q "health_check.sh"; then
        log "删除旧的cron任务..."
        crontab -l 2>/dev/null | grep -v "health_check.sh" | crontab -
    fi
    
    # 添加新的cron任务
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    
    log "✅ 已设置定时健康检查"
    info "检查频率: $CRON_SCHEDULE"
    info "查看cron任务: crontab -l"
    info "查看健康检查日志: tail -f $PROJECT_DIR/logs/health_check.log"
    echo ""
else
    log "跳过cron设置"
fi

# 3. 测试健康检查脚本
read -p "是否立即测试健康检查？(y/n) [y]: " test_health
test_health=${test_health:-y}

if [ "$test_health" = "y" ] || [ "$test_health" = "Y" ]; then
    log "运行健康检查测试..."
    bash "$PROJECT_DIR/health_check.sh"
    echo ""
fi

# 4. 切换到Gunicorn并重启服务
read -p "是否立即使用Gunicorn重启服务？(y/n，推荐) [y]: " restart_service
restart_service=${restart_service:-y}

if [ "$restart_service" = "y" ] || [ "$restart_service" = "Y" ]; then
    log "使用Gunicorn重启服务..."
    bash "$PROJECT_DIR/start_chatpd.sh" restart
    echo ""
fi

echo ""
echo "=========================================="
echo "  ✅ 监控系统设置完成！"
echo "=========================================="
echo ""

log "监控系统配置总结："
if [ "$install_systemd" = "y" ] || [ "$install_systemd" = "Y" ]; then
    info "✅ systemd服务已安装"
fi
if [ "$setup_cron" = "y" ] || [ "$setup_cron" = "Y" ]; then
    info "✅ 定时健康检查已配置"
fi

echo ""
log "下一步建议："
info "1. 查看服务状态: ./start_chatpd.sh status"
info "2. 查看健康检查日志: tail -f logs/health_check.log"
info "3. 监控应用日志: tail -f logs/app.log"
if [ "$install_systemd" = "y" ] || [ "$install_systemd" = "Y" ]; then
    info "4. 使用systemd管理: systemctl status chatpd"
fi

echo ""

