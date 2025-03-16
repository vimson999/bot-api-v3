"""
飞书签名验证模块

用于验证飞书API请求的签名，确保请求来自飞书服务器且未被篡改。
支持URL安全Base64编码的JWT样式token。

作者: [您的团队]
版本: 1.0.0
"""

import base64
import json
import logging
import time
import uuid
import threading
import functools
import os
from hmac import compare_digest

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 尝试导入主要加密库
try:
    from Crypto.PublicKey import RSA
    from Crypto.Signature import PKCS1_v1_5
    from Crypto.Hash import SHA256
    CRYPTO_LIB = "pycryptodome"
except ImportError:
    try:
        # 尝试备用加密库
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        CRYPTO_LIB = "cryptography"
    except ImportError:
        raise ImportError("需要安装加密库。请执行: pip install pycryptodome 或 pip install cryptography")


class FeishuSignatureConfig:
    """飞书签名验证配置"""
    
    # 默认公钥
    DEFAULT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxKNV23rheRvtUKDMJPOW
GhUt+W25k63X4Q1QYhztPlobF2VNIDR6eHVFUDP22aytzVguisJ/GaOKZ7FJDKis
9YvMUiCIFnfu1LWB4b4pa4ajmPk/Rr9DMSLz6frKRP0QqirWFe7t+u0K0nzzPe3/
a5ScSmJwYACmayQfLZFTFjyL0Z1SQFZM6pZ1J1w9ETxWI0NrpkMU7eqzVGvhf+OO
dmxsXrHARWa1Ldm3WqPCF3k5jKuPG7s0zB+iuBHamSitZ7ktBf0mzBBjsAjKQll1
kmdjryGbKX5sLXhEgOb5ndakYeA0Oy7vve2Hm78kH5MtaSv6MfNVjm5ForMjPAPQ
BQIDAQAB
-----END PUBLIC KEY-----"""

    # 安全限制
    MAX_TOKEN_SIZE = 10000   # 最大token长度
    MAX_DATA_SIZE = 8192     # 最大数据长度
    MAX_SIGNATURE_SIZE = 4096  # 最大签名长度
    
    # 性能配置
    VERIFY_TIMEOUT = 5.0     # 验证超时时间(秒)
    ENABLE_CACHING = True    # 是否启用缓存
    CACHE_SIZE = 128         # 缓存大小
    
    # 日志配置
    LOG_LEVEL = logging.INFO
    
    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        instance = cls()
        
        # 从环境变量读取配置
        instance.MAX_TOKEN_SIZE = int(os.getenv('FEISHU_MAX_TOKEN_SIZE', cls.MAX_TOKEN_SIZE))
        instance.MAX_DATA_SIZE = int(os.getenv('FEISHU_MAX_DATA_SIZE', cls.MAX_DATA_SIZE))
        instance.MAX_SIGNATURE_SIZE = int(os.getenv('FEISHU_MAX_SIGNATURE_SIZE', cls.MAX_SIGNATURE_SIZE))
        instance.VERIFY_TIMEOUT = float(os.getenv('FEISHU_VERIFY_TIMEOUT', cls.VERIFY_TIMEOUT))
        instance.ENABLE_CACHING = os.getenv('FEISHU_ENABLE_CACHING', 'true').lower() == 'true'
        instance.CACHE_SIZE = int(os.getenv('FEISHU_CACHE_SIZE', cls.CACHE_SIZE))
        
        # 日志级别
        log_level_name = os.getenv('FEISHU_LOG_LEVEL', 'INFO')
        instance.LOG_LEVEL = getattr(logging, log_level_name, logging.INFO)
        
        # 从环境变量或文件加载公钥
        key_path = os.getenv('FEISHU_PUBLIC_KEY_PATH')
        if key_path and os.path.exists(key_path):
            try:
                with open(key_path, 'r') as f:
                    instance.DEFAULT_PUBLIC_KEY = f.read().strip()
            except Exception as e:
                logger.warning(f"从文件加载公钥失败: {e}，将使用默认公钥")
                
        return instance


# 加载配置
config = FeishuSignatureConfig.from_env()
logger.setLevel(config.LOG_LEVEL)


class CryptoProvider:
    """
    加密操作提供者，隔离加密库依赖
    支持多种加密库实现，提高可靠性
    """
    
    @staticmethod
    def verify_rsa_signature(data, signature, public_key):
        """
        验证RSA签名
        
        参数:
            data (bytes): 原始数据字节
            signature (bytes): 签名字节
            public_key (str): PEM格式的公钥
        
        返回:
            bool: 验证结果
        """
        if CRYPTO_LIB == "pycryptodome":
            try:
                # 使用PyCryptodome实现
                key = RSA.import_key(public_key)
                verifier = PKCS1_v1_5.new(key)
                h = SHA256.new(data)
                return verifier.verify(h, signature)
            except Exception as e:
                logger.error(f"PyCryptodome验证失败: {e}")
                # 尝试备用实现
                return CryptoProvider._verify_with_cryptography(data, signature, public_key)
        else:
            # 使用cryptography实现
            return CryptoProvider._verify_with_cryptography(data, signature, public_key)
    
    @staticmethod
    def _verify_with_cryptography(data, signature, public_key):
        """使用cryptography库验证"""
        try:
            key = load_pem_public_key(public_key.encode())
            key.verify(
                signature,
                data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
        except Exception as e:
            logger.error(f"Cryptography验证失败: {e}")
            return False


# 缓存公钥加载结果
@functools.lru_cache(maxsize=config.CACHE_SIZE if config.ENABLE_CACHING else 0)
def load_public_key(public_key_pem):
    """
    加载并缓存公钥
    
    参数:
        public_key_pem (str): PEM格式的公钥
    
    返回:
        对象: 加载后的公钥对象
    """
    if CRYPTO_LIB == "pycryptodome":
        return RSA.import_key(public_key_pem)
    else:
        return load_pem_public_key(public_key_pem.encode())


def rsa_verify_sign(data, sign_data, public_key, debug=False):
    """
    验证RSA签名
    
    参数:
        data (str): 未编码的原始数据字符串
        sign_data (str): 签名的Base64编码字符串
        public_key (str): PEM格式的公钥
        debug (bool): 是否启用详细调试日志
    
    返回:
        bool: 验证是否成功
    """
    trace_id = request_ctx.get_trace_key()
    start_time = time.time()
    
    if debug:
        logger.setLevel(logging.DEBUG)
    
    # 安全检查 - 限制输入大小
    if len(data) > config.MAX_DATA_SIZE:
        logger.warning(f"[{trace_id}] 数据长度({len(data)})超过限制({config.MAX_DATA_SIZE})，可能存在DOS风险")
        return False
        
    if len(sign_data) > config.MAX_SIGNATURE_SIZE:
        logger.warning(f"[{trace_id}] 签名长度({len(sign_data)})超过限制({config.MAX_SIGNATURE_SIZE})，可能存在DOS风险")
        return False
    
    try:
        logger.debug(f"[{trace_id}] 开始验证签名")
        logger.debug(f"[{trace_id}] 原始数据: {data}")
        logger.debug(f"[{trace_id}] 原始签名(前50字符): {sign_data[:50]}...")
        
        # 创建哈希对象 - 对原始数据进行哈希
        data_bytes = data.encode('utf-8')
        
        # 处理URL安全的Base64编码
        safe_base64_sign = sign_data.replace('-', '+').replace('_', '/')
        logger.debug(f"[{trace_id}] 处理URL安全字符后的签名(前50字符): {safe_base64_sign[:50]}...")
        
        # 添加Base64 padding
        missing_padding = len(safe_base64_sign) % 4
        if missing_padding:
            safe_base64_sign += '=' * (4 - missing_padding)
            logger.debug(f"[{trace_id}] 添加了 {missing_padding} 个padding字符")
        
        # 解码签名
        try:
            signature = base64.b64decode(safe_base64_sign)
            logger.debug(f"[{trace_id}] 签名解码后的长度: {len(signature)} 字节")
        except Exception as e:
            logger.error(f"[{trace_id}] 签名Base64解码失败: {e}")
            return False
        
        # 验证签名
        result = CryptoProvider.verify_rsa_signature(data_bytes, signature, public_key)
        
        # 常量时间比较，防止计时攻击
        valid = compare_digest(str(result), str(True))
        
        duration = time.time() - start_time
        if valid:
            logger.info(f"[{trace_id}] 签名验证成功! 耗时: {duration:.4f}秒")
        else:
            logger.warning(f"[{trace_id}] 签名验证失败! 耗时: {duration:.4f}秒")
            
        # 性能监控
        if duration > 0.5:  # 超过500ms视为慢操作
            logger.warning(f"[{trace_id}] 签名验证耗时较长: {duration:.4f}秒")
            
        return valid
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[{trace_id}] 验证过程出错: {str(e)}, 耗时: {duration:.4f}秒", exc_info=debug)
        return False


def verify_feishu_token(token, debug=False, public_key=None, timeout=None):
    """
    验证飞书TOKEN
    
    参数:
        token (str): 飞书的JWT样式token
        debug (bool, optional): 是否启用详细调试日志. 默认为False.
        public_key (str, optional): 自定义公钥. 默认为None时使用内置公钥.
        timeout (float, optional): 验证超时时间(秒). 默认为None时使用配置中的超时时间.
    
    返回:
        tuple: (验证结果, 解码后的数据)
            - 验证结果 (bool): True表示验证成功，False表示验证失败
            - 解码后的数据 (dict或str或None): 成功时返回解码后的数据，失败时返回None
    
    异常:
        不抛出异常，所有错误都会被捕获并记录到日志
    
    安全性:
        - 验证RSA签名，确保数据未被篡改
        - 处理URL安全Base64编码
        - 超时保护防止长时间计算
    
    示例:
        >>> valid, data = verify_feishu_token(token)
        >>> if valid:
        ...     print(f"验证成功，数据: {data}")
        ... else:
        ...     print("验证失败")
    """
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    
    if debug:
        logger.setLevel(logging.DEBUG)
    
    # 使用提供的公钥或默认公钥
    if public_key is None:
        public_key = config.DEFAULT_PUBLIC_KEY
    
    # 使用提供的超时时间或配置中的超时时间
    if timeout is None:
        timeout = config.VERIFY_TIMEOUT
    
    # 输入验证
    if not token or not isinstance(token, str):
        logger.error(f"[{trace_id}] 无效的token输入")
        return False, None
    
    # 预处理token
    token = token.strip()
    
    # 安全检查 - 限制token大小
    if len(token) > config.MAX_TOKEN_SIZE:
        logger.error(f"[{trace_id}] token长度({len(token)})超过限制({config.MAX_TOKEN_SIZE})")
        return False, None
    
    logger.debug(f"[{trace_id}] 开始验证token: {token[:20]}...")
    
    # 使用线程带超时执行验证
    result = [False, None]
    error = [None]
    
    def _verify():
        try:
            # 分割token
            parts = token.split('.')
            if len(parts) != 2:
                logger.error(f"[{trace_id}] Token格式错误: 应有2个部分，实际有{len(parts)}个部分")
                return
            
            # 获取数据和签名部分
            encoded_data = parts[0]
            encoded_sign = parts[1]
            logger.debug(f"[{trace_id}] Token分割成功: 数据部分长度={len(encoded_data)}, 签名部分长度={len(encoded_sign)}")
            
            # 解码数据
            try:
                decoded_bytes = base64.b64decode(encoded_data)
                decoded_data = decoded_bytes.decode('utf-8')
                logger.debug(f"[{trace_id}] 数据解码成功: {decoded_data}")
                
                # 尝试解析JSON（仅用于日志，不影响验证）
                try:
                    json_data = json.loads(decoded_data)
                    logger.debug(f"[{trace_id}] JSON解析成功: {json_data}")
                except json.JSONDecodeError:
                    logger.warning(f"[{trace_id}] 数据不是有效的JSON格式")
            except Exception as e:
                logger.error(f"[{trace_id}] 数据解码失败: {str(e)}", exc_info=debug)
                return
            
            # 验证签名
            is_valid = rsa_verify_sign(decoded_data, encoded_sign, public_key, debug)
            
            if is_valid:
                try:
                    result[0] = True
                    result[1] = json.loads(decoded_data)
                except json.JSONDecodeError:
                    logger.warning(f"[{trace_id}] 数据不是有效的JSON格式，返回原始字符串")
                    result[0] = True
                    result[1] = decoded_data
            else:
                result[0] = False
                result[1] = None
        except Exception as e:
            error[0] = e
    
    # 启动验证线程
    verify_thread = threading.Thread(target=_verify)
    verify_thread.daemon = True
    verify_thread.start()
    verify_thread.join(timeout)
    
    if verify_thread.is_alive():
        duration = time.time() - start_time
        logger.error(f"[{trace_id}] 验证超时(>{timeout}秒), 实际耗时: {duration:.4f}秒")
        return False, None
    
    if error[0]:
        duration = time.time() - start_time
        logger.error(f"[{trace_id}] 验证过程异常: {error[0]}, 耗时: {duration:.4f}秒", exc_info=debug)
        return False, None
    
    duration = time.time() - start_time
    logger.info(f"[{trace_id}] 验证完成，结果: {result[0]}, 耗时: {duration:.4f}秒")
    
    return result[0], result[1]