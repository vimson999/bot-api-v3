"""
签名验证测试相关API路由
"""
from typing import Dict, Any, Optional
import time
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.decorators import TollgateConfig
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.core.signature import require_signature
from bot_api_v1.app.core.context import request_ctx

router = APIRouter(prefix="/sign", tags=["签名验证服务"])


class SignatureRequest(BaseModel):
    """签名验证请求模型"""
    message: str = Field(..., description="测试消息")
    data: Optional[Dict[str, Any]] = Field(None, description="附加数据，可选")
    

class SignatureResponse(BaseModel):
    """签名验证响应模型"""
    app_id: str
    message: str
    timestamp: int
    data: Optional[Dict[str, Any]] = None


@router.post(
    "/test/hmac_sha256",
    response_model=BaseResponse[SignatureResponse],
    responses={
        200: {"description": "HMAC-SHA256验签成功"},
        401: {"description": "验签失败"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="HMAC-SHA256验签测试",
    type="test",
    base_tollgate="10",
    current_tollgate="1",
    plat="api"
)
@require_signature(sign_type="hmac_sha256")
async def test_hmac_sha256(
    request: Request,
    data: SignatureRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    测试HMAC-SHA256签名验证功能
    
    此接口需要通过HMAC-SHA256签名验证才能访问。客户端需要：
    1. 设置X-App-ID请求头，提供应用ID
    2. 设置X-Signature请求头，提供签名
    3. 可选：设置X-Timestamp请求头，提供时间戳
    
    签名生成步骤：
    1. 构造待签名字符串：请求体 + "&timestamp=" + 时间戳
    2. 使用应用私钥和HMAC-SHA256算法生成签名
    3. 对签名进行Base64编码
    """
    trace_key = request_ctx.get_trace_key()
    logger.info(f"HMAC-SHA256验签测试通过", extra={"request_id": trace_key})
    
    app_id = request.state.app_id
    timestamp = request.headers.get("X-Timestamp", str(int(time.time())))
    
    return BaseResponse(
        code=200,
        message="HMAC-SHA256验签成功",
        data=SignatureResponse(
            app_id=app_id,
            message=data.message,
            timestamp=int(timestamp),
            data=data.data
        )
    )


@router.post(
    "/test/rsa",
    response_model=BaseResponse[SignatureResponse],
    responses={
        200: {"description": "RSA验签成功"},
        401: {"description": "验签失败"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="RSA验签测试",
    type="test",
    base_tollgate="10",
    current_tollgate="1",
    plat="api"
)
@require_signature(sign_type="rsa")
async def test_rsa(
    request: Request,
    data: SignatureRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    测试RSA签名验证功能
    
    此接口需要通过RSA签名验证才能访问。客户端需要：
    1. 设置X-App-ID请求头，提供应用ID
    2. 设置X-Signature请求头，提供签名
    3. 可选：设置X-Timestamp请求头，提供时间戳
    
    签名生成步骤：
    1. 构造待签名字符串：请求体 + "&timestamp=" + 时间戳
    2. 使用RSA私钥和SHA256算法生成签名
    3. 对签名进行Base64编码
    """
    trace_key = request_ctx.get_trace_key()
    logger.info(f"RSA验签测试通过", extra={"request_id": trace_key})
    
    app_id = request.state.app_id
    timestamp = request.headers.get("X-Timestamp", str(int(time.time())))
    
    return BaseResponse(
        code=200,
        message="RSA验签成功",
        data=SignatureResponse(
            app_id=app_id,
            message=data.message,
            timestamp=int(timestamp),
            data=data.data
        )
    )


@router.post(
    "/test/signature_info",
    response_model=BaseResponse,
    responses={
        200: {"description": "成功获取签名信息"},
        401: {"description": "验签失败"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="签名信息测试",
    type="test",
    base_tollgate="10",
    current_tollgate="1",
    plat="api"
)
@require_signature(exempt=True)  # 豁免验签，方便调试
async def test_signature_info(
    request: Request,
    data: SignatureRequest = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    获取签名调试信息
    
    此接口不要求签名验证，但会返回用于签名的相关信息，以便调试签名问题。
    """
    trace_key = request_ctx.get_trace_key()
    logger.info(f"请求签名信息测试", extra={"request_id": trace_key})
    
    # 获取请求相关信息
    headers = dict(request.headers)
    app_id = headers.get("x-app-id", "未提供")
    signature = headers.get("x-signature", "未提供")
    timestamp = headers.get("x-timestamp", str(int(time.time())))
    
    # 读取请求体
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")
    
    # 构造用于签名的字符串
    string_to_sign = f"{body_text}"
    if timestamp:
        string_to_sign = f"{string_to_sign}&timestamp={timestamp}"
    
    # 返回签名调试信息
    return BaseResponse(
        code=200,
        message="签名调试信息",
        data={
            "app_id": app_id,
            "timestamp": timestamp,
            "headers": headers,
            "body": body_text,
            "string_to_sign": string_to_sign,
            "signature": signature,
            "request_data": data.dict()
        }
    )


@router.get(
    "/generate/script",
    response_model=BaseResponse,
    responses={
        200: {"description": "成功生成签名测试脚本"},
        500: {"description": "服务器内部错误"}
    }
)
async def generate_test_script(
    app_id: str = Query(..., description="应用ID"),
    sign_type: str = Query("hmac_sha256", description="签名类型: hmac_sha256 或 rsa")
):
    """
    生成签名测试脚本
    
    此接口返回用于测试签名的Bash脚本，以便客户端测试签名验证功能。
    """
    # HMAC-SHA256测试脚本
    hmac_script = """#!/bin/bash

# 配置变量
APP_ID="{app_id}"
PRIVATE_KEY="test_secret_key"  # 请替换为您的实际私钥
API_URL="http://localhost:8000/api/sign/test/hmac_sha256"

# 生成当前时间戳
TIMESTAMP=$(date +%s)

# 准备请求体
BODY='{{"message":"测试HMAC-SHA256验签功能","data":{{"test":true}}}}'

# 生成签名字符串
SIGN_STRING="${{BODY}}&timestamp=${{TIMESTAMP}}"

# 将签名字符串写入临时文件
TEMP_FILE=$(mktemp)
echo -n "${{SIGN_STRING}}" > "${{TEMP_FILE}}"

# 使用HMAC-SHA256算法生成签名
SIGNATURE=$(cat "${{TEMP_FILE}}" | openssl dgst -sha256 -hmac "${{PRIVATE_KEY}}" -binary | base64)

# 清理临时文件
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
"""

    # RSA测试脚本
    rsa_script = """#!/bin/bash

# 配置变量
APP_ID="{app_id}"
PRIVATE_KEY_PATH="./rsa_key.private.pem"  # 请替换为您的RSA私钥路径
API_URL="http://localhost:8000/api/sign/test/rsa"

# 生成当前时间戳
TIMESTAMP=$(date +%s)

# 准备请求体
BODY='{{"message":"测试RSA验签功能","data":{{"test":true}}}}'

# 生成签名字符串
SIGN_STRING="${{BODY}}&timestamp=${{TIMESTAMP}}"

# 将签名字符串写入临时文件
TEMP_FILE=$(mktemp)
echo -n "${{SIGN_STRING}}" > "${{TEMP_FILE}}"

# 使用RSA私钥生成签名
SIGNATURE=$(openssl dgst -sha256 -sign "${{PRIVATE_KEY_PATH}}" "${{TEMP_FILE}}" | base64)

# 清理临时文件
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
"""
    
    # 根据签名类型返回对应的脚本
    script = hmac_script if sign_type == "hmac_sha256" else rsa_script
    script = script.format(app_id=app_id)
    
    return BaseResponse(
        code=200,
        message=f"成功生成{sign_type}签名测试脚本",
        data={
            "script": script,
            "sign_type": sign_type,
            "app_id": app_id,
            "instructions": "将此脚本保存为.sh文件，然后使用'sh script.sh'执行"
        }
    )


@router.get(
    "/generate/key",
    response_model=BaseResponse,
    responses={
        200: {"description": "成功生成RSA密钥生成脚本"},
        500: {"description": "服务器内部错误"}
    }
)
async def generate_rsa_key_script():
    """
    生成RSA密钥生成脚本
    
    此接口返回用于生成RSA密钥对的Python脚本，以便客户端测试RSA签名验证功能。
    """
    # RSA密钥生成脚本
    key_script = """#!/usr/bin/env python3
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import argparse
import os

def generate_rsa_keypair(output_dir, key_name="rsa_key", password=None):
    """生成RSA密钥对并保存到文件"""
    # 生成私钥
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # 如果提供了密码，使用密码加密私钥
    encryption = serialization.NoEncryption()
    if password:
        encryption = serialization.BestAvailableEncryption(password.encode())
    
    # 将私钥序列化为PEM格式
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption
    )
    
    # 从私钥获取公钥
    public_key = private_key.public_key()
    
    # 将公钥序列化为PEM格式
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存私钥到文件
    private_path = os.path.join(output_dir, f"{key_name}.private.pem")
    with open(private_path, 'wb') as f:
        f.write(pem_private)
    
    # 保存公钥到文件
    public_path = os.path.join(output_dir, f"{key_name}.public.pem")
    with open(public_path, 'wb') as f:
        f.write(pem_public)
    
    # 返回文件路径
    return private_path, public_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成RSA密钥对")
    parser.add_argument("--output", "-o", default=".", help="输出目录")
    parser.add_argument("--name", "-n", default="rsa_key", help="密钥名称")
    parser.add_argument("--password", "-p", help="私钥密码(可选)")
    
    args = parser.parse_args()
    
    private_path, public_path = generate_rsa_keypair(
        args.output,
        args.name,
        args.password
    )
    
    print(f"RSA密钥对已生成:")
    print(f"私钥: {private_path}")
    print(f"公钥: {public_path}")
    print("\\n您可以将公钥内容添加到数据库中的应用记录中:")
    
    # 显示公钥内容
    with open(public_path, 'r') as f:
        public_key = f.read()
        print(f"\\n{public_key}")
"""
    
    return BaseResponse(
        code=200,
        message=f"成功生成RSA密钥生成脚本",
        data={
            "script": key_script,
            "instructions": "将此脚本保存为generate_rsa_key.py，安装cryptography库后使用'python generate_rsa_key.py'执行"
        }
    )