#!/bin/bash

# 配置变量
APP_ID="16dad276-16e3-44d9-aefd-9fbee35ffb0b"
PRIVATE_KEY="test_secret_key"
API_URL="http://localhost:8000/api/script/test_signature"

# 生成当前时间戳
TIMESTAMP=$(date +%s)

# 准备请求体
BODY='{"message":"测试验签功能"}'

# 生成签名字符串
SIGN_STRING="${BODY}&timestamp=${TIMESTAMP}"

# 使用 Python 生成签名
SIGNATURE=$(python3 -c "
import hmac
import hashlib
import base64
private_key = '${PRIVATE_KEY}'
string_to_sign = '''${SIGN_STRING}'''
hmac_obj = hmac.new(
    private_key.encode('utf-8'),
    string_to_sign.encode('utf-8'),
    hashlib.sha256
)
print(base64.b64encode(hmac_obj.digest()).decode())
")

echo "Request URL: ${API_URL}"
echo "App ID: ${APP_ID}"
echo "Timestamp: ${TIMESTAMP}"
echo "Request Body: ${BODY}"
echo "Signature: ${SIGNATURE}"
echo "-----------------------------------"

curl -v -X POST "${API_URL}" \
  -H "Content-Type: application/json" \
  -H "X-App-ID: ${APP_ID}" \
  -H "X-Signature: ${SIGNATURE}" \
  -H "X-Timestamp: ${TIMESTAMP}" \
  -d "${BODY}"

echo