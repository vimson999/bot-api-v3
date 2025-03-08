#!/usr/bin/env python
"""
简单的签名验证测试工具
"""
import sys
import os
import json
import requests
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_api_v1.app.core.signature_tool import generate_hmac_sha256_signature

def test_signature():
    # 配置参数
    app_id = "16dad276-16e3-44d9-aefd-9fbee35ffb0b"  # 替换为你的实际app_id
    private_key = "test_secret_key"
    api_url = "http://localhost:8000/api/script/test_signature"
    message = "测试验签功能"
    
    # 准备请求体
    body = {"message": message}
    body_json = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    
    # 生成时间戳
    timestamp = int(time.time())
    
    # 生成签名
    string_to_sign = f"{body_json}&timestamp={timestamp}"
    signature = generate_hmac_sha256_signature(private_key, body_json, timestamp)
    
    # 准备请求头
    headers = {
        "Content-Type": "application/json",
        "X-App-ID": app_id,
        "X-Signature": signature,
        "X-Timestamp": str(timestamp)
    }
    
    # 输出信息
    print(f"请求URL: {api_url}")
    print(f"App ID: {app_id}")
    print(f"请求体: {body_json}")
    print(f"时间戳: {timestamp}")
    print(f"待签名字符串: {string_to_sign}")
    print(f"签名: {signature}")
    print("-" * 50)
    
    # 发送请求
    try:
        response = requests.post(api_url, json=body, headers=headers)
        
        # 输出响应
        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print(f"响应体: {response.text}")
        
        # 同时测试免验签接口
        print("\n测试免验签接口:")
        no_sig_response = requests.post(
            "http://localhost:8000/api/script/test_no_signature", 
            json=body
        )
        print(f"响应状态码: {no_sig_response.status_code}")
        print(f"响应体: {no_sig_response.text}")
        
    except Exception as e:
        print(f"请求异常: {str(e)}")

if __name__ == "__main__":
    test_signature()