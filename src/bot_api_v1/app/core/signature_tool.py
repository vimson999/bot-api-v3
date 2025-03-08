"""
签名生成工具

帮助客户端生成正确的API签名。
"""
import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional, Union


def generate_hmac_sha256_signature(
    private_key: str,
    body: Union[str, Dict, bytes],
    timestamp: Optional[int] = None
) -> str:
    """
    生成HMAC-SHA256签名
    
    Args:
        private_key: 私钥
        body: 请求体，可以是字符串、字典或字节
        timestamp: 时间戳，可选
    
    Returns:
        生成的签名
    """
    # 处理body参数
    if isinstance(body, dict):
        body_str = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    elif isinstance(body, bytes):
        body_str = body.decode('utf-8')
    else:
        body_str = str(body)
    
    # 构造待签名字符串
    string_to_sign = body_str
    if timestamp:
        string_to_sign = f"{string_to_sign}&timestamp={timestamp}"
    
    # 计算签名
    hmac_obj = hmac.new(
        private_key.encode(),
        string_to_sign.encode(),
        hashlib.sha256
    )
    signature = base64.b64encode(hmac_obj.digest()).decode()
    
    return signature


def generate_test_signature(app_id: str, private_key: str, message: str) -> Dict[str, Any]:
    """
    为测试接口生成签名和所需请求头
    
    Args:
        app_id: 应用ID
        private_key: 私钥
        message: 测试消息
    
    Returns:
        包含所需请求头的字典
    """
    # 创建请求体
    body = {"message": message}
    body_str = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    
    # 生成时间戳
    timestamp = int(time.time())
    
    # 生成签名
    signature = generate_hmac_sha256_signature(private_key, body_str, timestamp)
    
    # 返回请求头
    headers = {
        "X-App-ID": app_id,
        "X-Signature": signature,
        "X-Timestamp": str(timestamp),
        "Content-Type": "application/json"
    }
    
    return {
        "headers": headers,
        "body": body,
        "body_str": body_str,
        "timestamp": timestamp,
        "signature": signature,
        "curl_command": generate_curl_command(headers, body)
    }


def generate_curl_command(headers: Dict[str, str], body: Dict[str, Any]) -> str:
    """
    生成用于测试的curl命令
    
    Args:
        headers: 请求头
        body: 请求体
    
    Returns:
        完整的curl命令字符串
    """
    # 构建headers部分
    header_args = " ".join([f"-H '{k}: {v}'" for k, v in headers.items()])
    
    # 构建body部分
    body_json = json.dumps(body)
    
    # 组合curl命令
    curl_command = f"curl -X POST {header_args} -d '{body_json}' http://localhost:8000/api/script/test_signature"
    
    return curl_command


def debug_signature(app_id: str, private_key: str, body: str, timestamp: int, received_signature: str) -> Dict[str, Any]:
    """
    调试签名问题
    
    Args:
        app_id: 应用ID
        private_key: 私钥
        body: 请求体字符串
        timestamp: 时间戳
        received_signature: 收到的签名
        
    Returns:
        包含调试信息的字典
    """
    # 构造待签名字符串
    string_to_sign = f"{body}&timestamp={timestamp}"
    
    # 计算签名
    hmac_obj = hmac.new(
        private_key.encode(),
        string_to_sign.encode(),
        hashlib.sha256
    )
    expected_signature = base64.b64encode(hmac_obj.digest()).decode()
    
    # 比较签名
    signatures_match = hmac.compare_digest(expected_signature, received_signature)
    
    return {
        "app_id": app_id,
        "body": body,
        "timestamp": timestamp,
        "string_to_sign": string_to_sign,
        "expected_signature": expected_signature,
        "received_signature": received_signature,
        "signatures_match": signatures_match,
        "private_key_used": private_key,
    }


if __name__ == "__main__":
    """
    使用示例
    """
    # 示例应用信息
    app_id = "16dad276-16e3-44d9-aefd-9fbee35ffb0b"  # 替换为你的实际app_id
    private_key = "test_secret_key"  # 替换为你的实际私钥
    message = "测试验签功能"
    
    # 生成签名和测试信息
    result = generate_test_signature(app_id, private_key, message)
    
    print("=== 签名信息 ===")
    print(f"待签名字符串: {result['body_str']}&timestamp={result['timestamp']}")
    print(f"私钥: {private_key}")
    print(f"签名: {result['signature']}")
    
    print("\n=== 请求头 ===")
    for k, v in result["headers"].items():
        print(f"{k}: {v}")
    
    print("\n=== 请求体 ===")
    print(json.dumps(result["body"], ensure_ascii=False))
    
    print("\n=== CURL 命令 ===")
    print(result["curl_command"])