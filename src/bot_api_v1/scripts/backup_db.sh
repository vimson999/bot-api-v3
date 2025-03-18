#!/bin/bash
# PostgreSQL数据库备份脚本
# 建议通过crontab定期执行，例如每天凌晨3点：
# 0 3 * * * /code/bot_api/src/bot_api_v1/scripts/backup_db.sh >> /var/log/db_backups.log 2>&1

# 定义变量
BACKUP_DIR="/code/bot_api/backups"
DB_NAME="cappa_p_v1"
DB_USER="postgres"
DB_HOST="10.0.16.12"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"
LOG_FILE="$BACKUP_DIR/backup_history.log"
MAX_BACKUPS=7  # 保留的最大备份数量
RETENTION_DAYS=7  # 保留天数

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # 无颜色

# 确保备份目录存在
mkdir -p $BACKUP_DIR

# 记录开始时间
start_time=$(date +%s)
echo -e "${GREEN}[$(date +"%Y-%m-%d %H:%M:%S")] 开始备份数据库 $DB_NAME${NC}" | tee -a $LOG_FILE

# 创建备份
echo "正在创建备份..." | tee -a $LOG_FILE
PGPASSWORD="$PGPASSWORD" pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -c --if-exists | gzip > $BACKUP_FILE

# 检查备份是否成功
if [ $? -eq 0 ]; then
    # 获取备份文件大小
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    
    # 计算耗时
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    echo -e "${GREEN}[$(date +"%Y-%m-%d %H:%M:%S")] 备份完成: $BACKUP_FILE (大小: $BACKUP_SIZE, 耗时: ${duration}秒)${NC}" | tee -a $LOG_FILE
    
    # 对备份文件进行MD5校验
    MD5SUM=$(md5sum "$BACKUP_FILE" | cut -d' ' -f1)
    echo "备份文件MD5: $MD5SUM" | tee -a $LOG_FILE
    
    # 删除旧备份文件(基于数量)
    OLD_BACKUPS=$(ls -t $BACKUP_DIR/*.sql.gz | tail -n +$((MAX_BACKUPS+1)))
    if [ -n "$OLD_BACKUPS" ]; then
        echo "删除旧备份文件:" | tee -a $LOG_FILE
        for old_file in $OLD_BACKUPS; do
            echo "- 删除: $old_file" | tee -a $LOG_FILE
            rm -f "$old_file"
        done
    fi
    
    # 删除超过保留天数的备份文件
    find $BACKUP_DIR -name "*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete | tee -a $LOG_FILE
    
    # 列出当前所有备份
    CURRENT_BACKUPS=$(ls -lh $BACKUP_DIR/*.sql.gz 2>/dev/null | wc -l)
    echo "当前备份总数: $CURRENT_BACKUPS" | tee -a $LOG_FILE
    
    # 计算总占用空间
    TOTAL_SIZE=$(du -sh $BACKUP_DIR | cut -f1)
    echo "备份总占用空间: $TOTAL_SIZE" | tee -a $LOG_FILE
else
    echo -e "${RED}[$(date +"%Y-%m-%d %H:%M:%S")] 备份失败!${NC}" | tee -a $LOG_FILE
    exit 1
fi

echo -e "${GREEN}[$(date +"%Y-%m-%d %H:%M:%S")] 备份过程完成${NC}" | tee -a $LOG_FILE
echo "---------------------------------------------" | tee -a $LOG_FILE

exit 0