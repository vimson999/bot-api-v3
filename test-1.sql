select * from log_trace lt 
order by created_at desc 
limit 100;


INSERT INTO meta_app (
    name, 
    domain, 
    public_key, 
    private_key, 
    key_version, 
    status, 
    sign_type, 
    sign_config
) VALUES (
    'test_signature_app', 
    'localhost', 
    'test_public_key', 
    'test_secret_key', 
    1, 
    1, 
    'hmac_sha256', 
    '{"description": "用于验签测试"}'
);



select * from meta_app
WHERE 1=1
-- and name = 'test_signature_app'
AND id = '16dad276-16e3-44d9-aefd-9fbee35ffb0b'
order by created_at desc 
limit 100;









 git push bot-api-v3-github master:main;   

(venv) v9@v9deMacBook-Pro bot-api-v1 % uvicorn bot_api_v1.app.core.app:create_app --reload --host 0.0.0.0 --port 8000



curl -X POST "http://localhost:8000/api/script/transcribe" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -d '{"url": "https://www.youtube.com/shorts/O8GAUEDR0Is"}'


  {
    "version": "0.2.0",
    "configurations": [
      {
        "name": "FastAPI Debug (Async)",
        "type": "debugpy",
        "request": "launch",
        "program": "-m",
        "args": [
          "uvicorn",
          "bot_api_v1.app.core.app:create_app",
          "--reload",
          "--host=0.0.0.0",
          "--port=8000"
        ],
        "env": {
          "PYTHONPATH": "${workspaceFolder}/src"
        },
        "justMyCode": false,
        "console": "integratedTerminal",
        "cwd": "${workspaceFolder}",
        "asyncio": "enabled"  // 关键：启用异步调试支持
      }
    ]
  }




  # 从请求上下文获取tollgate信息
ctx = request_ctx.get_context()
base_tollgate = ctx.get('base_tollgate', tollgate.split('-')[0] if '-' in tollgate else '20')
current_tollgate = ctx.get('current_tollgate', '1')

# 如果找到base_tollgate和current_tollgate，递增current_tollgate
if base_tollgate and current_tollgate:
    try:
        new_tollgate = str(int(current_tollgate) + 1)
        # ctx['current_tollgate'] = new_tollgate
        # request_ctx.set_context(ctx)
        
        # 使用新的tollgate值
        if success:
            log_tollgate = f"{base_tollgate}-{new_tollgate}"
        else:
            log_tollgate = f"{base_tollgate}-9"
    except (ValueError, TypeError):
        # 如果转换失败，使用原始tollgate
        log_tollgate = tollgate if success else f"{tollgate.split('-')[0]}-9"
else:
    # 使用传入的tollgate参数
    log_tollgate = tollgate if success else f"{tollgate.split('-')[0]}-9"






# 从请求上下文获取tollgate信息
ctx = request_ctx.get_context()
base_tollgate = ctx.get('base_tollgate', tollgate.split('-')[0] if '-' in tollgate else '20')
current_tollgate = ctx.get('current_tollgate', '1')


new_tollgate = str(int(current_tollgate) + 1)
ctx['current_tollgate'] = new_tollgate
request_ctx.set_context(ctx)