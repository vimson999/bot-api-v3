#!/bin/bash

# 创建标准目录结构
mkdir -p src/bot_api_v1/{app/{api/routers,core,db,tasks,utils,middlewares,security},migrations,scripts,tests}

# 重命名错误文件（修复中文/特殊字符文件名）
mv src/bot-api-v1/src/bot-api-v1 src/bot_api_v1 2>/dev/null
find . -name "birthdays.*" -exec mv {} src/bot_api_v1/db/__init__.py \;
find . -name "elly事故发生.att" -exec mv {} src/bot_api_v1/tests/conftest.py \;

# 初始化必要文件
touch src/bot_api_v1/\
{app/__init__.py,\
app/api/__init__.py,\
app/core/__init__.py,\
app/db/__init__.py,\
app/tasks/__init__.py,\
app/utils/__init__.py,\
app/middlewares/__init__.py,\
app/security/__init__.py,\
migrations/README,\
scripts/run.sh,\
tests/__init__.py}

# 创建Alembic迁移配置
cat > src/bot_api_v1/alembic.ini << EOF
[alembic]
script_location = migrations
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic
EOF

# 初始化虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装基础依赖
cat > requirements.txt << EOF
fastapi>=0.68.0
uvicorn[standard]
sqlalchemy>=1.4.0
alembic>=1.7.0
python-dotenv>=0.19.0
celery[redis]
pytest>=6.2.0
asyncpg>=0.25.0
aioredis>=2.0.0
EOF

pip install -r requirements.txt

# 安全处理
echo ".env" >> .gitignore
git init 2>/dev/null

# 设置执行权限
chmod +x src/bot_api_v1/scripts/run.sh

echo "目录结构调整完成！请检查以下事项："
echo "1. 检查自动重命名的文件（特别是原中文文件名文件）"
echo "2. 编辑 src/bot_api_v1/core/config.py 配置数据库连接"
echo "3. 运行 'source venv/bin/activate' 激活虚拟环境"
echo "4. 初始化数据库：alembic upgrade head"