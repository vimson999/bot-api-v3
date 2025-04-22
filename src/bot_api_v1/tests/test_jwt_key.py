import secrets
# 生成32字节 (256位) 的URL安全Base64编码密钥
key = secrets.token_urlsafe(32)
print(key)

