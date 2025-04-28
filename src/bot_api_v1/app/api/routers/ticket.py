from fastapi import APIRouter, Request
from jose import jwt
from datetime import datetime, timedelta
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger

router = APIRouter(prefix="/tkt", tags=["票据"])

SECRET_KEY = settings.SITE_JS_SECRET_KEY  # 配置中设置
ALGORITHM = "HS256"

@router.get("/get_ticket", summary="获取用于前端加密的临时票据", tags=["安全与授权"])
async def get_ticket(request: Request):
    """
    生成一个短时效的、绑定客户端IP的JWT票据，用于前端加密请求。
    """
    expire = datetime.utcnow() + timedelta(minutes=10) # 10分钟有效期
    client_host = request.client.host if request.client else "unknown_ip"
    payload = {
        "exp": expire,
        "ip": client_host, # 绑定IP地址
        "sub": "frontend_media_request" # 标识票据用途
    }

    logger.debug(f"get_ticket----生成前端加密票据----payload----: {payload}")

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"get_ticket----生成前端加密票据----token----: {token}")

    return {"ticket": token}