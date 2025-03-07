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


def generate_test_signature(app_id: str, private_key: str, message: str) -> Dict[str, str]:
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
    
    # 生成时间戳
    timestamp = int(time.time())
    
    # 生成签名
    signature = generate_hmac_sha256_signature(private_key, body, timestamp)
    
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


if __name__ == "__main__":
    """
    使用示例
    """
    # 示例应用信息
    app_id = "YOUR_APP_ID"
    private_key = "YOUR_PRIVATE_KEY"
    message = "Hello, world!"
    
    # 生成签名和测试命令
    result = generate_test_signature(app_id, private_key, message)
    
    print("=== 请求头 ===")
    for k, v in result["headers"].items():
        print(f"{k}: {v}")
    
    print("\n=== 请求体 ===")
    print(json.dumps(result["body"], indent=2))
    
    print("\n=== CURL 命令 ===")
    print(result["curl_command"])