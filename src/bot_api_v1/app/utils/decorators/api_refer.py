from functools import wraps
from fastapi import Request, HTTPException, Header
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from jose import jwt, JWTError

import base64
import hashlib
import json
from datetime import datetime, timedelta
from functools import wraps

from fastapi import (APIRouter, Depends, Header, HTTPException, Request,
                   status)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from jose import jwt, JWTError
from pydantic import BaseModel, Field # 用于定义解密请求体模型

SECRET_KEY = settings.SITE_JS_SECRET_KEY
ALGORITHM = "HS256"

# --- 解密和验证逻辑 ---

class EncryptedData(BaseModel):
    """定义前端发送的加密数据结构"""
    data: str = Field(..., description="Base64 编码的 AES 加密数据")
    iv: str = Field(..., description="Base64 编码的 AES 初始化向量 (IV)")

def _decrypt_data(encrypted_base64: str, iv_base64: str, key: bytes) -> bytes:
    """使用 AES-256-CBC 解密数据"""
    backend = default_backend()
    try:
        iv = base64.b64decode(iv_base64)
        ciphertext = base64.b64decode(encrypted_base64)
    except (base64.binascii.Error, ValueError) as e:
        logger.warning(f"解密失败：IV或密文Base64解码错误: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的加密数据格式 (base64)")

    if len(iv) != 16: # AES block size is 16 bytes
         logger.warning(f"解密失败：IV 长度错误 ({len(iv)} bytes)")
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的加密数据格式 (iv length)")

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    decryptor = cipher.decryptor()

    try:
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    except ValueError as e: # Handle potential errors during finalization (e.g., tag mismatch in GCM, though we use CBC)
        logger.warning(f"解密失败：解密操作失败: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="解密操作失败")

    # Unpadding (PKCS7)
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    try:
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    except ValueError as e: # Handle padding errors
        logger.warning(f"解密失败：无效的填充 (Padding Error): {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的加密数据 (padding)")

    return plaintext

async def decrypt_and_validate_request(
    request: Request,
    encrypted_body: EncryptedData, # FastAPI 会自动解析请求体到这个模型
    x_ticket: str = Header(None, description="从 /api/ticket/get_ticket 获取的 JWT")
) -> dict:
    """
    FastAPI 依赖项：
    1. 验证 X-Ticket (JWT 签名, 有效期, IP 绑定).
    2. 从 X-Ticket 派生 AES 密钥.
    3. 使用密钥和请求体中的 IV 解密请求体中的 data.
    4. 返回解密后的数据字典.
    """
    if not x_ticket:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="缺少 X-Ticket 头")

    client_host = request.client.host if request.client else "unknown_ip"

    try:
        # 1. 验证 JWT Ticket
        payload = jwt.decode(
            x_ticket,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": True, "verify_signature": True}
        )
        # 检查 IP 绑定
        ticket_ip = payload.get("ip")
        if ticket_ip != client_host:
            logger.warning(f"Ticket IP 不匹配: 票据IP='{ticket_ip}', 请求IP='{client_host}'")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ticket IP 不匹配")
        # 可选：检查 'sub' 或其他声明
        if payload.get("sub") != "frontend_media_request":
             logger.warning(f"Ticket 用途不匹配: sub='{payload.get('sub')}'")
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ticket 用途不正确")

        logger.debug(f"Ticket 验证通过: {payload}")
    except JWTError as e:
        logger.warning(f"无效或过期的 Ticket: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Ticket 无效或已过期: {e}")
    except Exception as e: # 其他潜在错误
        logger.error(f"Ticket 验证时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ticket 验证失败")

    try:
        # 2. 从 Ticket 派生 AES-256 密钥 (使用 SHA-256 哈希)
        #    确保与前端使用相同的方式
        key = hashlib.sha256(x_ticket.encode('utf-8')).digest() # 32 bytes key

        logger.debug(f"encrypted_body 解密之前 ---: {encrypted_body}")
        # 3. 解密数据
        decrypted_data_bytes = _decrypt_data(encrypted_body.data, encrypted_body.iv, key)

        # 4. 将解密的 bytes 解析为 JSON (字典)
        decrypted_payload = json.loads(decrypted_data_bytes.decode('utf-8'))
        logger.debug(f"decrypted_payload解密成功: {decrypted_payload}")

        return decrypted_payload

    except HTTPException: # 重新抛出 _decrypt_data 中已定义的 HTTPException
        raise
    except json.JSONDecodeError:
        logger.warning("解密失败：解密后的数据不是有效的 JSON")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的加密内容 (非 JSON)")
    except Exception as e:
        logger.error(f"解密过程中发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="处理加密请求时出错")


# --- require_api_security (基本不变, 但现在配合 Ticket 使用) ---
# 这个装饰器现在提供第二层防护：检查来源和静态 Token
def require_api_security(
    allowed_domains=None,
):
    if allowed_domains is None:
        # 从配置加载，提供默认值以防万一
        allowed_domains = getattr(settings, "ALLOWED_ORIGINS", [settings.DEV_URL, settings.DOMAIN_MAIN_URL, settings.DOMAIN_IP_URL, settings.DOMAIN_API_URL])
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request, x_api_token: str = Header(None), **kwargs):
            # 检查 Origin (更可靠的跨域来源检查)
            origin = request.headers.get("origin")
            if allowed_domains and (not origin or not any(origin.startswith(domain) for domain in allowed_domains)):
                 logger.warning(f"Origin 校验失败: {origin}. Allowed: {allowed_domains}")
                 # 注意：对于非浏览器客户端（如 curl），Origin 可能不存在，根据需要调整策略
                 # if not origin and "curl" in request.headers.get("user-agent","").lower():
                 #     pass # Allow curl for testing? Be careful.
                 # else:
                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Invalid Origin")

            # Referer 检查 (可以作为辅助，但 Origin 更可靠)
            referer = request.headers.get("referer", "")
            if allowed_domains and not any(referer.startswith(domain) for domain in allowed_domains):
                # Referer 可以被省略或伪造，所以警告即可，不一定阻止
                logger.debug(f"Referer 校验未通过 (可能为空或来自非预期来源): {referer}. Allowed: {allowed_domains}")
                # raise HTTPException(status_code=403, detail="Forbidden: Invalid Referer") # 酌情启用

            logger.debug(f"require_api_security passed for {request.url}")
            # 注意：这里不再需要传递 x_api_token 给内部函数，除非它确实需要
            return await func(*args, request=request, **kwargs)
            # 如果内部函数确实需要 x_api_token:
            # return await func(*args, request=request, x_api_token=x_api_token, **kwargs)
        return wrapper
    return decorator
