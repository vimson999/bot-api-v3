#!/usr/bin/env python3
import hmac
import hashlib
import base64
import subprocess
import sys
import json
import time
import os

def hexdump(data):
    """以十六进制格式打印二进制数据"""
    result = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        result.append(f"{i:04x}: {hex_str:<48} {ascii_str}")
    return '\n'.join(result)

# 测试数据
private_key = "test_secret_key"
body = '{"message":"测试验签功能aaaaaa"}'
timestamp = str(int(time.time()))  # 使用当前时间戳
string_to_sign = f"{body}&timestamp={timestamp}"

print(f"=== 签名诊断工具 ===")
print(f"操作系统: {sys.platform}")
print(f"Python 版本: {sys.version}")
print(f"私钥: {private_key}")
print(f"请求体: {body}")
print(f"时间戳: {timestamp}")
print(f"待签名字符串: {string_to_sign}")

print("\n=== 编码信息 ===")
print(f"待签名字符串UTF-8编码:")
print(hexdump(string_to_sign.encode('utf-8')))
print(f"\n私钥UTF-8编码:")
print(hexdump(private_key.encode('utf-8')))

# Python 方式
print("\n=== Python HMAC-SHA256 签名过程 ===")
hmac_obj = hmac.new(
    private_key.encode('utf-8'),
    string_to_sign.encode('utf-8'),
    hashlib.sha256
)
digest = hmac_obj.digest()
print(f"HMAC-SHA256 摘要 (十六进制):")
print(hexdump(digest))

py_signature = base64.b64encode(digest).decode()
print(f"\nBase64 编码后: {py_signature}")

# 使用文件的 OpenSSL 方式
print("\n=== OpenSSL 文件方式签名过程 ===")
try:
    # 创建临时文件避免命令行注入
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w+') as temp:
        temp.write(string_to_sign)
        temp.flush()
        
        # 打印文件内容，确认没有问题
        print(f"临时文件路径: {temp.name}")
        print(f"文件内容:")
        with open(temp.name, 'rb') as f:
            file_content = f.read()
            print(hexdump(file_content))
        
        # macOS OpenSSL 命令
        cmd = f'cat {temp.name} | openssl dgst -sha256 -hmac "{private_key}" -binary | base64'
        print(f"\n执行命令: {cmd}")
        openssl_signature = subprocess.check_output(cmd, shell=True).decode().strip()
        print(f"结果: {openssl_signature}")
        
except Exception as e:
    print(f"OpenSSL 命令执行失败: {str(e)}")
    openssl_signature = "执行失败"

# 直接使用echo的OpenSSL方式
print("\n=== OpenSSL echo方式签名过程 ===")
try:
    echo_cmd = f'echo -n "{string_to_sign}" | openssl dgst -sha256 -hmac "{private_key}" -binary | base64'
    print(f"执行命令: {echo_cmd}")
    echo_openssl_signature = subprocess.check_output(echo_cmd, shell=True).decode().strip()
    print(f"结果: {echo_openssl_signature}")
    
    # 保存echo输出到文件以检查实际传递的内容
    echo_debug_cmd = f'echo -n "{string_to_sign}" > /tmp/echo_debug.txt'
    subprocess.run(echo_debug_cmd, shell=True)
    print(f"\necho输出保存到: /tmp/echo_debug.txt")
    print(f"echo输出内容:")
    with open('/tmp/echo_debug.txt', 'rb') as f:
        echo_content = f.read()
        print(hexdump(echo_content))
    
except Exception as e:
    print(f"Echo OpenSSL 命令执行失败: {str(e)}")
    echo_openssl_signature = "执行失败"

# 比较各种方式
print("\n=== 签名结果对比 ===")
print(f"Python 签名:      {py_signature}")
print(f"OpenSSL 文件签名: {openssl_signature}")
print(f"OpenSSL echo签名: {echo_openssl_signature}")
print(f"Python/OpenSSL文件 匹配: {py_signature == openssl_signature}")
print(f"Python/OpenSSL echo 匹配: {py_signature == echo_openssl_signature}")
print(f"OpenSSL两种方式 匹配: {openssl_signature == echo_openssl_signature}")

# 如果不匹配，检查每个字节
if py_signature != echo_openssl_signature:
    print("\n=== 签名二进制对比 (Python vs OpenSSL echo) ===")
    py_bytes = base64.b64decode(py_signature)
    try:
        echo_bytes = base64.b64decode(echo_openssl_signature)
        print("Python 签名二进制:")
        print(hexdump(py_bytes))
        print("\nOpenSSL echo 签名二进制:")
        print(hexdump(echo_bytes))
        
        print("\n差异分析:")
        min_len = min(len(py_bytes), len(echo_bytes))
        
        if len(py_bytes) != len(echo_bytes):
            print(f"长度不同: Python={len(py_bytes)}, OpenSSL echo={len(echo_bytes)}")
        
        differences = []
        for i in range(min_len):
            if py_bytes[i] != echo_bytes[i]:
                differences.append(f"位置 {i}: Python={py_bytes[i]:02x}, OpenSSL echo={echo_bytes[i]:02x}")
        
        if differences:
            print("差异位置:")
            for diff in differences:
                print(diff)
            print(f"共有 {len(differences)} 个差异")
        else:
            print("共同部分内容相同")
    except Exception as e:
        print(f"无法比较二进制内容: {str(e)}")

# 生成标准测试命令
print("\n=== 用于测试的参数 ===")
print(f"APP_ID: 16dad276-16e3-44d9-aefd-9fbee35ffb0b")
print(f"时间戳: {timestamp}")
print(f"签名: {py_signature}")

# Python方式的curl命令
py_curl_cmd = f'''
curl -v -X POST "http://localhost:8000/api/script/test_signature" \\
  -H "Content-Type: application/json" \\
  -H "X-App-ID: 16dad276-16e3-44d9-aefd-9fbee35ffb0b" \\
  -H "X-Signature: {py_signature}" \\
  -H "X-Timestamp: {timestamp}" \\
  -d '{body}'
'''

# 文件方式的OpenSSL生成签名的shell脚本
shell_script = f'''#!/bin/bash

# 配置变量
APP_ID="16dad276-16e3-44d9-aefd-9fbee35ffb0b"
PRIVATE_KEY="test_secret_key"
API_URL="http://localhost:8000/api/script/test_signature"

# 生成当前时间戳
TIMESTAMP="{timestamp}"

# 准备请求体
BODY='{body}'

# 生成签名字符串
SIGN_STRING="${{BODY}}&timestamp=${{TIMESTAMP}}"

# 使用临时文件 + OpenSSL（可靠方式）
TEMP_FILE=$(mktemp)
echo -n "${{SIGN_STRING}}" > "${{TEMP_FILE}}"
SIGNATURE=$(cat "${{TEMP_FILE}}" | openssl dgst -sha256 -hmac "${{PRIVATE_KEY}}" -binary | base64)
rm "${{TEMP_FILE}}"

# 打印请求信息
echo "Request URL: ${{API_URL}}"
echo "App ID: ${{APP_ID}}"
echo "Timestamp: ${{TIMESTAMP}}"
echo "Request Body: ${{BODY}}"
echo "Signature: ${{SIGNATURE}}"
echo "-----------------------------------"

# 发送请求
curl -v -X POST "${{API_URL}}" \\
  -H "Content-Type: application/json" \\
  -H "X-App-ID: ${{APP_ID}}" \\
  -H "X-Signature: ${{SIGNATURE}}" \\
  -H "X-Timestamp: ${{TIMESTAMP}}" \\
  -d "${{BODY}}"

echo
'''

print("\n=== 测试命令 ===")
print("Python方式的curl命令:")
print(py_curl_cmd)

print("\n文件方式的OpenSSL签名脚本 (推荐):")
script_path = "/tmp/test_signature.sh"
with open(script_path, 'w') as f:
    f.write(shell_script)
os.chmod(script_path, 0o755)
print(f"脚本已保存到: {script_path}")
print("可以直接执行: sh " + script_path)

print("\n=== 诊断完成 ===")