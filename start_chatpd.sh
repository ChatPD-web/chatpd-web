#!/bin/bash

# ChatPD Web App 一键启动脚本
# 作者: ChatPD Team
# 版本: 1.0

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 设置项目路径
PROJECT_DIR="/root/web_app/web_chatpd"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$PROJECT_DIR/logs/chatpd.pid"
LOG_FILE="$PROJECT_DIR/logs/app.log"

# 创建必要目录
mkdir -p "$LOG_DIR"

# 打印日志函数
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# 检查依赖
check_dependencies() {
    log "检查系统依赖..."
    
    if ! command -v python3 &> /dev/null; then
        error "Python3 未安装"
        exit 1
    fi
    
    if ! python3 -c "import flask, flask_cors" 2>/dev/null; then
        error "Flask 或 flask-cors 未安装"
        info "正在安装依赖..."
        pip3 install flask flask-cors
    fi
    
    if ! python3 -c "import sqlite3" 2>/dev/null; then
        error "SQLite3 支持未安装"
        exit 1
    fi
    
    log "✅ 依赖检查完成"
}

# 检查数据库
check_database() {
    log "检查数据库..."
    
    if [ ! -f "$PROJECT_DIR/data/chatpd_data.db" ]; then
        error "数据库文件不存在: $PROJECT_DIR/data/chatpd_data.db"
        exit 1
    fi
    
    log "✅ 数据库检查完成"
}

# 检查SSL证书
check_ssl() {
    log "检查SSL证书..."
    
    CERT_PATH="/etc/letsencrypt/live/testweb.241814.xyz/fullchain.pem"
    KEY_PATH="/etc/letsencrypt/live/testweb.241814.xyz/privkey.pem"
    
    if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
        warn "SSL证书未找到，将使用开发模式 (HTTP)"
        export FLASK_ENV=development
        return 1
    else
        log "✅ SSL证书检查完成"
        export FLASK_ENV=production
        return 0
    fi
}

# 停止现有进程
stop_service() {
    log "停止现有服务..."
    
    # 通过PID文件停止
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            sleep 2
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID"
            fi
            log "✅ 已停止进程 PID: $PID"
        fi
        rm -f "$PID_FILE"
    fi
    
    # 通过进程名停止（Flask和Gunicorn）
    if pgrep -f "src.web_app.search_engine" > /dev/null; then
        pkill -f "src.web_app.search_engine"
        sleep 2
        log "✅ 已停止所有相关进程"
    fi
    
    # 停止Gunicorn进程（如果存在）
    if pgrep -f "gunicorn.*search_engine" > /dev/null; then
        pkill -f "gunicorn.*search_engine"
        sleep 2
        log "✅ 已停止Gunicorn进程"
    fi
}

# 启动服务
start_service() {
    log "启动ChatPD服务..."
    
    cd "$PROJECT_DIR" || exit 1
    
    # 清理旧日志
    if [ -f "$LOG_FILE" ]; then
        if [ $(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null) -gt 10485760 ]; then # 10MB
            mv "$LOG_FILE" "$LOG_FILE.old"
            log "日志文件已轮转"
        fi
    fi
    
    # 检查是否使用Gunicorn
    if command -v gunicorn &> /dev/null; then
        # 使用Gunicorn生产服务器（推荐）
        nohup bash -c "
            export FLASK_ENV=$FLASK_ENV
            export PYTHONPATH=$PROJECT_DIR
            cd $PROJECT_DIR
            gunicorn -c gunicorn_config.py src.web_app.search_engine:app
        " > "$LOG_FILE" 2>&1 &
        log "使用Gunicorn生产服务器"
    else
        # 降级使用Flask开发服务器
        warn "Gunicorn未安装，使用Flask开发服务器（不推荐生产环境）"
        nohup bash -c "
            export FLASK_ENV=$FLASK_ENV
            export PYTHONPATH=$PROJECT_DIR
            cd $PROJECT_DIR
            python3 -m src.web_app.search_engine
        " > "$LOG_FILE" 2>&1 &
    fi
    
    # 记录PID
    echo $! > "$PID_FILE"
    
    sleep 3
    
    # 检查是否启动成功
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            log "✅ 服务启动成功 PID: $PID"
            return 0
        else
            error "服务启动失败"
            return 1
        fi
    else
        error "无法创建PID文件"
        return 1
    fi
}

# 检查服务状态
check_status() {
    log "检查服务状态..."
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            log "✅ 服务正在运行 PID: $PID"
            
            # 检查端口
            if netstat -tuln | grep -q ":5000 "; then
                log "✅ 端口5000正在监听"
            else
                warn "端口5000未监听"
            fi
            
            # 测试API
            if [ "$FLASK_ENV" = "production" ]; then
                TEST_URL="https://localhost:5000/api/filters"
            else
                TEST_URL="http://localhost:5000/api/filters"
            fi
            
            if curl -k -s --connect-timeout 5 "$TEST_URL" | grep -q "top_data_types"; then
                log "✅ API接口正常响应"
                log "🚀 ChatPD服务完全正常！"
                
                if [ "$FLASK_ENV" = "production" ]; then
                    info "🌐 外网访问地址: https://testweb.241814.xyz:5000"
                    info "🔒 使用HTTPS加密连接"
                else
                    info "🌐 本地访问地址: http://localhost:5000"
                    info "⚠️  开发模式，仅HTTP连接"
                fi
                
                return 0
            else
                error "API接口无响应"
                return 1
            fi
        else
            error "服务进程不存在"
            return 1
        fi
    else
        error "PID文件不存在"
        return 1
    fi
}

# 显示日志
show_logs() {
    log "显示最近50行日志..."
    if [ -f "$LOG_FILE" ]; then
        tail -50 "$LOG_FILE"
    else
        warn "日志文件不存在"
    fi
}

# 配置防火墙
configure_firewall() {
    log "配置防火墙..."
    
    if command -v firewall-cmd &> /dev/null; then
        if firewall-cmd --zone=public --add-port=5000/tcp --permanent 2>/dev/null; then
            firewall-cmd --reload 2>/dev/null
            log "✅ 防火墙已配置端口5000"
        fi
    else
        warn "firewall-cmd 未找到，请手动配置防火墙"
    fi
}

# 主菜单
show_menu() {
    echo ""
    echo -e "${BLUE}=== ChatPD Web App 管理脚本 ===${NC}"
    echo -e "${GREEN}1.${NC} 启动服务"
    echo -e "${GREEN}2.${NC} 停止服务"
    echo -e "${GREEN}3.${NC} 重启服务"
    echo -e "${GREEN}4.${NC} 查看状态"
    echo -e "${GREEN}5.${NC} 查看日志"
    echo -e "${GREEN}6.${NC} 配置防火墙"
    echo -e "${GREEN}0.${NC} 退出"
    echo ""
}

# 主函数
main() {
    case "$1" in
        "start")
            check_dependencies
            check_database
            check_ssl
            configure_firewall
            stop_service
            start_service
            check_status
            ;;
        "stop")
            stop_service
            ;;
        "restart")
            check_dependencies
            check_database
            check_ssl
            stop_service
            start_service
            check_status
            ;;
        "status")
            check_status
            ;;
        "logs")
            show_logs
            ;;
        "firewall")
            configure_firewall
            ;;
        *)
            if [ $# -eq 0 ]; then
                # 交互模式
                while true; do
                    show_menu
                    read -p "请选择操作 [0-6]: " choice
                    case $choice in
                        1)
                            main start
                            ;;
                        2)
                            main stop
                            ;;
                        3)
                            main restart
                            ;;
                        4)
                            main status
                            ;;
                        5)
                            main logs
                            ;;
                        6)
                            main firewall
                            ;;
                        0)
                            log "再见！"
                            exit 0
                            ;;
                        *)
                            error "无效选择"
                            ;;
                    esac
                    echo ""
                    read -p "按Enter继续..." dummy
                done
            else
                echo "用法: $0 {start|stop|restart|status|logs|firewall}"
                echo ""
                echo "命令说明:"
                echo "  start     - 启动ChatPD服务"
                echo "  stop      - 停止ChatPD服务"
                echo "  restart   - 重启ChatPD服务"
                echo "  status    - 查看服务状态"
                echo "  logs      - 查看日志"
                echo "  firewall  - 配置防火墙"
                echo ""
                echo "或者直接运行脚本进入交互模式"
                exit 1
            fi
            ;;
    esac
}

# 执行主函数
main "$@" 