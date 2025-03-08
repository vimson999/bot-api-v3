"""
签名验证模块

为API提供签名验证功能，支持多种验签算法，适配不同外部服务商。
"""

import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional, Type, Callable
import functools
from datetime import datetime, timedelta

from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.db.session import get_db

from bot_api_v1.app.models.meta_app import MetaApp
from uuid import UUID


class SignatureVerifier:
    """签名验证基类"""

    # 验签器注册表
    _verifiers: Dict[str, Type["SignatureVerifier"]] = {}

    @classmethod
    def register(cls, name: str):
        """注册验签器装饰器"""

        def decorator(verifier_cls):
            cls._verifiers[name] = verifier_cls
            return verifier_cls

        return decorator

    @classmethod
    async def get_verifier(
        cls, app_id: str, sign_type: str = None, db: Optional[AsyncSession] = None
    ) -> "SignatureVerifier":
        """
        根据app_id和签名类型获取对应的验签器

        Args:
            app_id: 应用ID
            sign_type: 签名类型，为None时使用应用默认配置
            db: 数据库会话

        Returns:
            对应的验签器实例

        Raises:
            ValueError: 如果找不到应用或验签器
        """
        from bot_api_v1.app.models.meta_app import MetaApp
        from bot_api_v1.app.db.session import get_db, async_session_maker
        from uuid import UUID

        trace_key = request_ctx.get_trace_key()
        logger.debug(
            f"获取验签器: app_id={app_id}, sign_type={sign_type}",
            extra={"request_id": trace_key},
        )

        # 处理db可能是上下文管理器的情况
        session_to_close = None
        try:
            # 如果db是上下文管理器，尝试获取实际会话
            if hasattr(db, "__aenter__"):
                async with db as session:
                    db = session

            # 如果db仍然为None或不可用，创建新会话
            if db is None or not hasattr(db, "execute"):
                db = async_session_maker()
                session_to_close = db

            # 使用异步查询方法获取应用信息
            stmt = select(MetaApp).where(MetaApp.id == UUID(app_id))
            result = await db.execute(stmt)
            app = result.scalar_one_or_none()

            if not app:
                logger.error(f"应用不存在: {app_id}", extra={"request_id": trace_key})
                raise ValueError(f"应用不存在: {app_id}")

            logger.debug(
                f"成功获取应用信息: name={app.name}", extra={"request_id": trace_key}
            )

            # 获取应用配置
            app_info = {
                "id": str(app.id),
                "name": app.name,
                "public_key": app.public_key,
                "private_key": app.private_key,
                "key_version": app.key_version,
                "domain": app.domain,
            }

            # 检查应用状态
            if app.status != 1:
                logger.error(
                    f"应用状态异常: {app.status}", extra={"request_id": trace_key}
                )
                raise ValueError(f"应用状态异常: {app.status}")

            # 从app_info添加sign_type和sign_config
            if app.sign_type:
                app_info["sign_type"] = app.sign_type

            if app.sign_config:
                app_info["sign_config"] = app.sign_config

            # 如果未指定签名类型，尝试从应用配置获取
            app_sign_type = sign_type
            if not app_sign_type and app.sign_type:
                app_sign_type = app.sign_type
                logger.debug(
                    f"使用应用配置的sign_type: {app_sign_type}",
                    extra={"request_id": trace_key},
                )

            # 如果还没有签名类型，从sign_config尝试获取
            if not app_sign_type:
                try:
                    if app.sign_config:
                        logger.debug(
                            f"尝试从sign_config解析签名类型",
                            extra={"request_id": trace_key},
                        )
                        if isinstance(app.sign_config, dict):
                            config = app.sign_config
                        else:
                            config = json.loads(app.sign_config)
                        app_sign_type = config.get("default_sign_type", "hmac_sha256")
                    else:
                        app_sign_type = "hmac_sha256"  # 默认使用HMAC-SHA256
                        logger.debug(
                            f"使用默认签名类型: {app_sign_type}",
                            extra={"request_id": trace_key},
                        )
                except Exception as e:
                    logger.error(
                        f"解析签名配置失败: {str(e)}",
                        extra={"request_id": trace_key},
                        exc_info=True,
                    )
                    app_sign_type = "hmac_sha256"  # 解析失败时使用默认值

            # 获取验签器类
            logger.debug(
                f"查找验签器: {app_sign_type}", extra={"request_id": trace_key}
            )
            verifier_cls = cls._verifiers.get(app_sign_type)
            if not verifier_cls:
                # 如果找不到指定的验签器，使用默认验签器
                logger.warning(
                    f"找不到验签器: {app_sign_type}，使用默认验签器",
                    extra={"request_id": trace_key},
                )
                verifier_cls = cls._verifiers.get("hmac_sha256", DefaultVerifier)

            # 创建验签器实例
            logger.debug(
                f"创建验签器实例: {verifier_cls.__name__}",
                extra={"request_id": trace_key},
            )
            return verifier_cls(app_info)

        except Exception as e:
            logger.error(
                f"获取验签器失败: {str(e)}",
                extra={"request_id": trace_key},
                exc_info=True,
            )
            raise
        finally:
            # 关闭自动创建的会话
            if session_to_close is not None:
                try:
                    await session_to_close.close()
                except Exception as e:
                    logger.warning(f"关闭会话时出错: {str(e)}")

    def __init__(self, app_info: Dict[str, Any]):
        """
        初始化验签器

        Args:
            app_info: 应用信息，包含密钥等
        """
        self.app_info = app_info

    async def verify(self, request: Request) -> bool:
        """
        验证请求签名

        Args:
            request: FastAPI请求对象

        Returns:
            验证是否通过
        """
        raise NotImplementedError("子类必须实现verify方法")


class DefaultVerifier(SignatureVerifier):
    """默认验签器，用于未指定验签类型时"""

    async def verify(self, request: Request) -> bool:
        """默认验签逻辑，简单检查app_id匹配"""
        trace_key = request_ctx.get_trace_key()
        logger.debug("使用默认验签器验证", extra={"request_id": trace_key})

        app_id = request.headers.get("X-App-ID")
        result = app_id == self.app_info["id"]

        logger.debug(f"默认验签结果: {result}", extra={"request_id": trace_key})
        return result


@SignatureVerifier.register("hmac_sha256")
class HmacSha256Verifier(SignatureVerifier):
    """HMAC-SHA256验签器"""

    async def verify(self, request: Request) -> bool:
        """
        使用HMAC-SHA256算法验证签名

        步骤:
        1. 获取请求中的签名和时间戳
        2. 验证时间戳有效性
        3. 构造待签名字符串（参数按字母排序）
        4. 使用应用私钥生成签名
        5. 比较生成的签名与请求提供的签名

        Args:
            request: FastAPI请求对象

        Returns:
            验证是否通过
        """
        trace_key = request_ctx.get_trace_key()
        logger.debug("使用HMAC-SHA256验证签名", extra={"request_id": trace_key})

        # 获取请求头中的签名和时间戳
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")

        if not signature:
            logger.warning("缺少签名", extra={"request_id": trace_key})
            raise ValueError("缺少签名")

        logger.debug(f"收到签名: {signature}", extra={"request_id": trace_key})
        logger.debug(f"收到时间戳: {timestamp}", extra={"request_id": trace_key})

        # 验证时间戳（可选）
        if timestamp:
            try:
                ts = int(timestamp)
                current_ts = int(time.time())
                # 时间戳不能超过5分钟
                if abs(current_ts - ts) > 300:
                    logger.warning(
                        f"时间戳已过期: {timestamp}", extra={"request_id": trace_key}
                    )
                    return False
            except Exception as e:
                logger.warning(
                    f"无效的时间戳: {timestamp}", extra={"request_id": trace_key}
                )
                return False

        # 获取密钥
        private_key = self.app_info.get("private_key")
        if not private_key:
            logger.error("应用缺少私钥", extra={"request_id": trace_key})
            raise ValueError("应用缺少私钥")

        try:
            # 读取请求体
            body = await request.body()
            body_text = body.decode("utf-8")
            logger.debug(f"请求体: {body_text}", extra={"request_id": trace_key})

            # 构造待签名字符串
            string_to_sign = f"{body_text}"
            if timestamp:
                string_to_sign = f"{string_to_sign}&timestamp={timestamp}"

            logger.debug(
                f"待签名字符串: {string_to_sign}", extra={"request_id": trace_key}
            )

            # 修改：打印更多调试信息
            logger.debug(f"使用的密钥: {private_key}", extra={"request_id": trace_key})

            # 计算签名 - 尝试调整编码方式
            hmac_obj = hmac.new(
                private_key.encode("utf-8"),  # 显式指定 UTF-8 编码
                string_to_sign.encode("utf-8"),  # 显式指定 UTF-8 编码
                hashlib.sha256,
            )
            expected_signature = base64.b64encode(hmac_obj.digest()).decode()

            # 额外添加：尝试使用 Shell 脚本中相同的方式生成签名进行对比
            test_signature = None
            try:
                import subprocess

                if sys.platform == "darwin":  # macOS
                    cmd = f'echo -n "{string_to_sign}" | openssl dgst -sha256 -hmac "{private_key}" -binary | base64'
                else:  # Linux
                    cmd = f'echo -n "{string_to_sign}" | openssl dgst -sha256 -mac HMAC -macopt "key:{private_key}" -binary | base64'
                test_signature = (
                    subprocess.check_output(cmd, shell=True).decode().strip()
                )
                logger.debug(
                    f"OpenSSL 生成的签名: {test_signature}",
                    extra={"request_id": trace_key},
                )
            except Exception as e:
                logger.warning(
                    f"无法使用 OpenSSL 生成测试签名: {str(e)}",
                    extra={"request_id": trace_key},
                )

                logger.debug(
                    f"预期签名: {expected_signature}", extra={"request_id": trace_key}
                )
            logger.debug(f"收到的签名: {signature}", extra={"request_id": trace_key})

            # 先用我们生成的签名验证
            result = hmac.compare_digest(expected_signature, signature)

            # 如果我们的签名验证失败，尝试用 OpenSSL 方式生成的签名验证
            if not result and test_signature:
                alt_result = hmac.compare_digest(test_signature, signature)
                logger.debug(
                    f"OpenSSL 签名验证结果: {alt_result}",
                    extra={"request_id": trace_key},
                )
                if alt_result:
                    # 如果 OpenSSL 方式验证成功，我们知道问题在签名生成算法上
                    logger.warning(
                        "Python 和 OpenSSL 的签名生成方式不一致！",
                        extra={"request_id": trace_key},
                    )
                    result = alt_result  # 临时措施：使用 OpenSSL 方式验证结果

            logger.debug(f"签名比对结果: {result}", extra={"request_id": trace_key})

            return result

        except Exception as e:
            logger.error(
                f"验签过程出错: {str(e)}",
                extra={"request_id": trace_key},
                exc_info=True,
            )
            raise

@SignatureVerifier.register("rsa")
class RsaVerifier(SignatureVerifier):
    """RSA签名验证器"""
    
    async def verify(self, request: Request) -> bool:
        """
        使用RSA算法验证签名
        
        步骤:
        1. 获取请求中的签名和时间戳
        2. 验证时间戳有效性
        3. 构造待签名字符串
        4. 使用应用公钥验证签名
        
        Args:
            request: FastAPI请求对象
        
        Returns:
            验证是否通过
        """
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.exceptions import InvalidSignature
        
        trace_key = request_ctx.get_trace_key()
        logger.debug("使用RSA验证签名", extra={"request_id": trace_key})
        
        # 获取请求头中的签名和时间戳
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        
        if not signature:
            logger.warning("缺少签名", extra={"request_id": trace_key})
            raise ValueError("缺少签名")
        
        logger.debug(f"收到签名: {signature}", extra={"request_id": trace_key})
        logger.debug(f"收到时间戳: {timestamp}", extra={"request_id": trace_key})
        
        # 验证时间戳（可选）
        if timestamp:
            try:
                ts = int(timestamp)
                current_ts = int(time.time())
                # 时间戳不能超过5分钟
                if abs(current_ts - ts) > 300:
                    logger.warning(
                        f"时间戳已过期: {timestamp}", extra={"request_id": trace_key}
                    )
                    return False
            except Exception as e:
                logger.warning(
                    f"无效的时间戳: {timestamp}", extra={"request_id": trace_key}
                )
                return False
        
        # 获取公钥
        public_key_pem = self.app_info.get("public_key")
        if not public_key_pem:
            logger.error("应用缺少公钥", extra={"request_id": trace_key})
            raise ValueError("应用缺少公钥")
        
        # 确保公钥格式正确（添加PEM头尾如果没有）
        if not public_key_pem.startswith("-----BEGIN PUBLIC KEY-----"):
            public_key_pem = (
                "-----BEGIN PUBLIC KEY-----\n" + 
                public_key_pem + 
                "\n-----END PUBLIC KEY-----"
            )
        
        try:
            # 读取请求体
            body = await request.body()
            body_text = body.decode("utf-8")
            logger.debug(f"请求体: {body_text}", extra={"request_id": trace_key})
            
            # 构造待签名字符串
            string_to_sign = f"{body_text}"
            if timestamp:
                string_to_sign = f"{string_to_sign}&timestamp={timestamp}"
            
            logger.debug(
                f"待验证字符串: {string_to_sign}", extra={"request_id": trace_key}
            )
            
            # 解码Base64签名
            signature_bytes = base64.b64decode(signature)
            
            # 加载公钥
            public_key = load_pem_public_key(public_key_pem.encode("utf-8"))
            
            # 验证签名
            try:
                public_key.verify(
                    signature_bytes,
                    string_to_sign.encode("utf-8"),
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                logger.debug("RSA签名验证通过", extra={"request_id": trace_key})
                return True
            except InvalidSignature:
                logger.warning("RSA签名验证失败", extra={"request_id": trace_key})
                return False
            
        except Exception as e:
            logger.error(
                f"RSA验证过程出错: {str(e)}",
                extra={"request_id": trace_key},
                exc_info=True,
            )
            raise

def require_signature(sign_type: str = None, exempt: bool = False):
    """
    验签装饰器，用于API路由函数

    Args:
        sign_type: 指定验签类型，为None时使用应用默认配置
        exempt: 是否豁免验签，设为True时跳过验签

    Returns:
        装饰器函数

    用法:
        @router.post("/api/endpoint")
        @require_signature(sign_type="hmac_sha256")
        async def endpoint(request: Request):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 如果豁免验签，直接执行原函数
            if exempt:
                return await func(*args, **kwargs)

            # 获取请求对象
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                for key, value in kwargs.items():
                    if isinstance(value, Request):
                        request = value
                        break

            if not request:
                logger.error("无法获取请求对象")
                raise HTTPException(status_code=400, detail="无法获取请求对象")

            # 获取trace_key用于日志
            trace_key = request_ctx.get_trace_key()
            logger.debug(
                f"开始验证签名，trace_key={trace_key}", extra={"request_id": trace_key}
            )

            # 获取app_id
            app_id = request.headers.get("X-App-ID")
            if not app_id:
                logger.warning("验签失败: 缺少App ID", extra={"request_id": trace_key})
                raise HTTPException(status_code=401, detail="缺少App ID")

            logger.debug(
                f"处理app_id={app_id}的验签请求", extra={"request_id": trace_key}
            )

            try:
                # 获取数据库会话
                db = kwargs.get("db")
                if not db:
                    # 如果没有通过依赖注入获取db，尝试创建一个
                    logger.debug(
                        "通过函数创建数据库会话", extra={"request_id": trace_key}
                    )
                    try:
                        # db_func = get_db()
                        # db = await db_func.__anext__()
                        # async with get_db() as db:
                        async for db in get_db():
                            logger.debug(
                                "成功创建数据库会话", extra={"request_id": trace_key}
                            )
                    except Exception as e:
                        logger.error(
                            f"创建数据库会话失败: {str(e)}",
                            extra={"request_id": trace_key},
                            exc_info=True,
                        )
                        raise ValueError(f"无法创建数据库会话: {str(e)}")

                # 获取验签器
                logger.debug(
                    f"获取验签器1: app_id={app_id}, sign_type={sign_type}",
                    extra={"request_id": trace_key},
                )
                try:
                    verifier = await SignatureVerifier.get_verifier(
                        app_id, sign_type, db
                    )
                    logger.debug(
                        f"成功获取验签器: {type(verifier).__name__}",
                        extra={"request_id": trace_key},
                    )
                except Exception as e:
                    logger.error(
                        f"获取验签器失败: {str(e)}",
                        extra={"request_id": trace_key},
                        exc_info=True,
                    )
                    if isinstance(e, ValueError):
                        raise HTTPException(status_code=401, detail=str(e))
                    raise

                # 执行验签
                logger.debug("开始执行验签", extra={"request_id": trace_key})
                try:
                    signature_valid = await verifier.verify(request)
                    logger.debug(
                        f"验签结果: {signature_valid}", extra={"request_id": trace_key}
                    )
                    if not signature_valid:
                        logger.warning(
                            f"验签失败: {app_id}", extra={"request_id": trace_key}
                        )
                        raise HTTPException(status_code=401, detail="签名验证失败")
                except ValueError as e:
                    logger.error(
                        f"验签参数错误: {str(e)}", extra={"request_id": trace_key}
                    )
                    raise HTTPException(status_code=401, detail=str(e))
                except Exception as e:
                    logger.error(
                        f"验签执行异常: {str(e)}",
                        extra={"request_id": trace_key},
                        exc_info=True,
                    )
                    raise

                # 验签通过，记录日志
                logger.info(f"验签通过: {app_id}", extra={"request_id": trace_key})

                # 将app_id存入请求状态，供后续处理使用
                request.state.app_id = app_id

                # 执行原始处理函数
                return await func(*args, **kwargs)

            except HTTPException:
                # 直接重新抛出HTTP异常
                raise

            except ValueError as e:
                logger.error(f"验签错误: {str(e)}", extra={"request_id": trace_key})
                raise HTTPException(status_code=401, detail=str(e))

            except Exception as e:
                logger.error(
                    f"验签过程发生异常: {str(e)}",
                    extra={"request_id": trace_key},
                    exc_info=True,
                )
                raise HTTPException(status_code=500, detail="验签过程发生内部错误")

        return wrapper

    return decorator
