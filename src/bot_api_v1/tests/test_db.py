# 创建一个简单的测试脚本如 test_db.py
import asyncio
from bot_api_v1.app.db.session import check_db_connection

async def test():
    result = await check_db_connection()
    print(f"Database connection: {'SUCCESS' if result else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(test())
