#!/bin/bash
# bot_api 部署脚本 - 用于更新代码和重启服务
# 使用方法: ./deploy.sh [branch]
# branch参数默认为master

set -e  # 遇到错误立即停止

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # 无颜色

# 获取开始时间
start_time=$(date +%s)

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 处理命令行参数
BRANCH=${1:-master}  # 默认为master分支
log_info "使用分支: $BRANCH"

# 定义工作目录
WORK_DIR="/code/bot_api"
APP_DIR="$WORK_DIR"

# 切换到工作目录
cd $WORK_DIR
log_info "当前工作目录: $(pwd)"

# 获取当前git提交哈希，用于回滚
CURRENT_COMMIT=$(git rev-parse HEAD)
log_info "当前Git提交: $CURRENT_COMMIT"

# 备份当前环境文件
if [ -f .env ]; then
    cp .env .env.backup
    log_info "已备份 .env 文件"
fi

# 拉取最新代码
log_info "正在拉取最新代码..."
git fetch --all
git checkout $BRANCH
git pull origin $BRANCH

# 获取新的git提交哈希
NEW_COMMIT=$(git rev-parse HEAD)
log_info "更新到Git提交: $NEW_COMMIT"

# 如果有新变化
if [ "$CURRENT_COMMIT" != "$NEW_COMMIT" ]; then
    log_info "检测到代码变更，准备更新依赖..."
    
    # 激活虚拟环境
    source venv/bin/activate
    log_info "虚拟环境已激活"
    
    # 更新依赖
    log_info "正在更新依赖..."
    pip install -r requirements.txt
    
    # 导出当前依赖版本（备份）
    pip freeze > requirements.freeze
    log_info "当前依赖已备份到 requirements.freeze"
else
    log_info "代码未变更，跳过依赖更新"
fi

# 确保PYTHONPATH设置正确
export PYTHONPATH=$WORK_DIR/src:$PYTHONPATH

# 重启服务前进行测试
log_info "正在测试服务是否可以启动..."
if python -c "import bot_api_v1.app.core.app_factory; print('导入成功')" 2>/dev/null; then
    log_info "导入测试成功"
else
    log_error "导入测试失败，可能存在代码问题。正在回滚..."
    # 回滚代码
    git checkout $CURRENT_COMMIT
    # 恢复环境文件
    if [ -f .env.backup ]; then
        mv .env.backup .env
    fi
    log_error "已回滚到提交: $CURRENT_COMMIT"
    exit 1
fi

# 重启服务
log_info "正在重启服务..."
sudo systemctl restart bot_api

# 等待服务启动
sleep 3

# 检查服务状态
if sudo systemctl is-active --quiet bot_api; then
    log_info "服务已成功重启"
    
    # 测试健康检查API
    log_info "正在测试健康检查API..."
    HEALTH_CHECK=$(curl -s -X GET "http://localhost:8000/api/health" \
                 -H "Content-Type: application/json" \
                 -H "x-source: deployment" \
                 -H "x-app-id: deployment-script" \
                 -H "x-user-uuid: system")
    
    if [[ $HEALTH_CHECK == *"\"status\":\"healthy\""* ]]; then
        log_info "健康检查通过"
    else
        log_warn "健康检查返回异常响应:"
        echo $HEALTH_CHECK
        log_warn "服务可能未正确启动，但未回滚。请手动检查"
    fi
else
    log_error "服务启动失败，正在回滚..."
    # 回滚代码
    git checkout $CURRENT_COMMIT
    # 恢复环境文件
    if [ -f .env.backup ]; then
        mv .env.backup .env
    fi
    # 尝试启动服务
    sudo systemctl restart bot_api
    log_error "已回滚到提交: $CURRENT_COMMIT"
    exit 1
fi

# 计算耗时
end_time=$(date +%s)
duration=$((end_time - start_time))

log_info "部署完成！耗时 ${duration} 秒"
log_info "API服务运行在 http://101.35.56.140:8000"
log_info "可以通过以下命令查看服务日志:"
log_info "sudo journalctl -u bot_api -f"

# 清理备份文件
if [ -f .env.backup ]; then
    rm .env.backup
fi

exit 0