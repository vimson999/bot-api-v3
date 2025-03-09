import base64
import json
import logging
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA256
from bot_api_v1.app.core.logger import logger


def rsa_verify_sign(data, sign_data, public_key, debug=False):
    """
    验证RSA签名
    
    参数:
    data: 未编码的原始数据字符串
    sign_data: 签名的Base64编码字符串
    public_key: PEM格式的公钥
    debug: 是否启用详细调试日志
    
    返回:
    bool: 验证是否成功
    """
    if debug:
        logger.setLevel(logging.DEBUG)
    
    try:
        logger.debug(f"开始验证签名")
        logger.debug(f"原始数据: {data}")
        logger.debug(f"原始签名(前50字符): {sign_data[:50]}...")
        
        # 加载RSA公钥
        key = RSA.import_key(public_key)
        logger.debug(f"公钥加载成功，模数长度: {key.n.bit_length()} 位")
        
        # 创建验证器
        verifier = PKCS1_v1_5.new(key)
        
        # 创建哈希对象 - 对原始数据进行哈希
        h = SHA256.new(data.encode('utf-8'))
        logger.debug(f"数据SHA256哈希值: {h.hexdigest()}")
        
        # 处理URL安全的Base64编码
        safe_base64_sign = sign_data.replace('-', '+').replace('_', '/')
        logger.debug(f"处理URL安全字符后的签名(前50字符): {safe_base64_sign[:50]}...")
        
        # 添加Base64 padding
        missing_padding = len(safe_base64_sign) % 4
        if missing_padding:
            safe_base64_sign += '=' * (4 - missing_padding)
            logger.debug(f"添加了 {missing_padding} 个padding字符")
        
        # 解码签名
        signature = base64.b64decode(safe_base64_sign)
        logger.debug(f"签名解码后的长度: {len(signature)} 字节")
        
        # 验证签名
        result = verifier.verify(h, signature)
        if result:
            logger.info("签名验证成功!")
        else:
            logger.warning("签名验证失败!")
        return result
    except Exception as e:
        logger.error(f"验证过程出错: {str(e)}", exc_info=debug)
        return False

def verify_feishu_token(token, debug=False):
    """
    验证飞书TOKEN
    
    参数:
    token: 飞书的JWT样式token
    debug: 是否启用详细调试日志
    
    返回:
    tuple: (验证结果, 解码后的数据)
    """
    if debug:
        logger.setLevel(logging.DEBUG)
    
    # Base的公钥
    base_public_key = """-----BEGIN PUBLIC KEY-----
    MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxKNV23rheRvtUKDMJPOW
    GhUt+W25k63X4Q1QYhztPlobF2VNIDR6eHVFUDP22aytzVguisJ/GaOKZ7FJDKis
    9YvMUiCIFnfu1LWB4b4pa4ajmPk/Rr9DMSLz6frKRP0QqirWFe7t+u0K0nzzPe3/
    a5ScSmJwYACmayQfLZFTFjyL0Z1SQFZM6pZ1J1w9ETxWI0NrpkMU7eqzVGvhf+OO
    dmxsXrHARWa1Ldm3WqPCF3k5jKuPG7s0zB+iuBHamSitZ7ktBf0mzBBjsAjKQll1
    kmdjryGbKX5sLXhEgOb5ndakYeA0Oy7vve2Hm78kH5MtaSv6MfNVjm5ForMjPAPQ
    BQIDAQAB
    -----END PUBLIC KEY-----"""
    
    logger.debug(f"开始验证token: {token[:20]}...")
    
    # 分割token
    parts = token.split('.')
    if len(parts) != 2:
        logger.error(f"Token格式错误: 应有2个部分，实际有{len(parts)}个部分")
        return False, None
    
    # 获取数据和签名部分
    encoded_data = parts[0]
    encoded_sign = parts[1]
    logger.debug(f"Token分割成功: 数据部分长度={len(encoded_data)}, 签名部分长度={len(encoded_sign)}")
    
    # 解码数据
    try:
        decoded_bytes = base64.b64decode(encoded_data)
        decoded_data = decoded_bytes.decode('utf-8')
        logger.debug(f"数据解码成功: {decoded_data}")
        
        # 尝试解析JSON（仅用于日志，不影响验证）
        try:
            json_data = json.loads(decoded_data)
            logger.debug(f"JSON解析成功: {json_data}")
        except json.JSONDecodeError:
            logger.warning("数据不是有效的JSON格式")
    except Exception as e:
        logger.error(f"数据解码失败: {str(e)}", exc_info=debug)
        return False, None
    
    # 验证签名
    is_valid = rsa_verify_sign(decoded_data, encoded_sign, base_public_key, debug)
    
    if is_valid:
        try:
            return True, json.loads(decoded_data)
        except json.JSONDecodeError:
            logger.warning("数据不是有效的JSON格式，返回原始字符串")
            return True, decoded_data
    else:
        return False, None

# 示例使用
if __name__ == "__main__":
    # 要验签的数据
    test_token = 'eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoicmVwbGl0XzNlNzFkZWYyODU2Y2UzZjQiLCJleHAiOjE3MjUzNjUyMjUyNjh9.Q6ixsDOiKg4EzI7L5xg9EfIkajPz1Eu6W4jPYFEx69sVFpqC516l4TBic-C5kLh2uPnSg6EVt5tasXXkjAFG9C7wBLalu1PHr1TmQ_2FkPfhlirQf1y9GL4WudvtLWgGjy2G2yGkw-tqiBaYb6YcbBuEAOTQ4kU6ohkn6SkckI01cl_6qDsUjb_m885Xr8kqoJSgkFDYzLLQB5LIZHI6d7JAOekCyTeuxPn-xxCohamyJUzZSJ9jxtX2aS-8F6UkAh6ta_VmhIDDsSeGN-ZyzEq_iV_Zzz4T3XkFWASdJmfm_l78OQcfoMKhBVhBB8p0G1uJII0lLcvTd01WVb7WUg=='
    
    # 设置为True开启详细日志
    valid, data = verify_feishu_token(test_token, debug=True)
    
    print("\n验证结果:", "成功" if valid else "失败")
    if valid:
        print("解码数据:", data)
        if isinstance(data, dict) and 'exp' in data:
            print("过期时间:", data['exp'])